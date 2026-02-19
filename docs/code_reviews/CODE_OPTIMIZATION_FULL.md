Below is a short, prioritised “next-up” list based on the code-review notes and what we just learned while tuning the chart path.  Most of these are low-risk, high-impact tweaks you can slot in incrementally.

──────────────────────────────────
1. Order-Book Pipeline
──────────────────────────────────
A. OrderBookProcessor  
• Already uses NumPy, but it still converts the raw `bids` / `asks` lists to two new arrays on every update.  
 → Keep two pre-allocated buffers and fill them in-place (`np.resize` / slicing) when level counts vary.  
 → When aggregation state hasn’t changed, skip re-sorting: bids come in price-DESC, asks price-ASC—both already monotonic.

• Spread filter: build a slice index with `np.searchsorted` instead of boolean masks.

B. OrderBookWidget  
• You now push **all** (x,y) arrays into `dpg.set_value` every tick.  
 → Keep references returned by `dpg.add_*_series`, then only update the *tail* chunk that changed (`dpg.set_value_part`), same trick as chart.  
• If aggregation flag is OFF, render depth only every N frames (checkbox “full book realtime”). Users rarely need millisecond resolution of the entire ladder.

──────────────────────────────────
2. PriceLevelWidget table
──────────────────────────────────
• `_aggregate_order_book` currently builds Python `dict`s each update.  
 → Port that to NumPy like the processor; you’ll gain ~5–8× speed.

• Row update loop: batch-update values with `dpg.set_table_row` (will land in 1.11) or cache tags in two flat lists, then use `dpg.set_values` to update *columns* with single C-calls.

• Consider pushing actual rendering to another thread (DPG is thread-safe if you guard with `dpg.lock_mutex()` / `unlock_mutex()`) so heavy  depth merges don’t block the GUI thread.

──────────────────────────────────
3. TaskManager & SignalEmitter
──────────────────────────────────
• Replace the `asyncio.Queue` consumer with `loop.call_soon_threadsafe(emitter.emit, …)` directly from the worker tasks. Eliminates a busy-wait coroutine.  

• Introduce a **Signal object pool** (fixed deque) to recycle dicts/tuples and reduce GC churn.

──────────────────────────────────
4. CandleFactory follow-ups
──────────────────────────────────
• Swap Pandas DF for a fixed-size NumPy structured array or PyArrow table. Pandas is still handy for resample, but for realtime append it’s over-kill.

• Push initial history to GPU-compressed Parquet (via `pyarrow`) to slash loading times at start-up.

──────────────────────────────────
5. Backend / CCXT
──────────────────────────────────
• If an exchange supports websocket **diff** order-book streams (`depthUpdate`, `l2Updates`) subscribe to them instead of periodic full snapshots; feed the diff straight into the processor.  

## Coinbase Order Book Feeds: How CCXT Utilizes Snapshots and Differential Updates

Coinbase's Advanced Trade platform provides order book data through websocket feeds, offering initial full snapshots followed by differential updates. This method, used by CCXT's `watch_order_book` function, efficiently maintains a local order book by processing only the changes in price levels. The `level2` channel in Coinbase's API ensures reliable updates, reducing data transmission compared to periodic full snapshots. CCXT leverages this by establishing a websocket connection to receive snapshots and updates, allowing for real-time order book accuracy without frequent REST API calls. This approach aligns with efficient order book processing using websocket diff streams.

• Use `uvloop` on *nix (drop-in `import uvloop, asyncio; uvloop.install()`).

──────────────────────────────────
6. Profiling & Tooling
──────────────────────────────────
• Add a `--profile` CLI flag that starts `yappi` and dumps a flamegraph on exit.  
• Integrate `tracemalloc` snapshots around high-frequency loops to watch for unintended allocations.

──────────────────────────────────
Quick-Wins Checklist
──────────────────────────────────
[ ] Pre-allocated NumPy buffers in OrderBookProcessor  
[ ] Incremental `dpg.set_value_part` (not real) updates for order-book series  
[ ] NumPy-based aggregation in PriceLevelWidget  
[ ] Replace `asyncio.Queue` poll with `call_soon_threadsafe`  
[ ] Object-pool small payload dicts in SignalEmitter  

Let me know which item you want to tackle first—or if you’d like me to prototype one of them right away!


---------------------------------------------------

Below is a “shopping list” of background reading + concrete design notes you can keep at hand before we start ripping out pandas and re-wiring the order-book path.  Skim the references that look new to you; they’ll save us time when we implement.

──────────────────────────────────────────────
A.  Candles without pandas
──────────────────────────────────────────────
1.  Data structure  
    • Use a single, fixed-size NumPy structured array or a ctypes/`dataclasses` + NumPy view:  
      ```python
      dtype = np.dtype([("ts", "int64"),      # seconds
                        ("o",  "float64"),
                        ("h",  "float64"),
                        ("l",  "float64"),
                        ("c",  "float64"),
                        ("v",  "float64")])
      buf = np.zeros(MAX_CANDLES, dtype=dtype)
      head = 0        # index of current candle
      count = 0       # how many valid rows
      ```

    • Resizing strategy: circular-buffer that doubles when full, or just cap at e.g., 20 000 ( ~14 days of 1-second candles ).

2.  EMA incremental update  
    `ema_next = α*close + (1-α)*ema_prev`.  
    Keep a dict `{span: value}` → one multiply per trade instead of recomputing on full vector.

3.  Conversion for DearPyGui  
    `dpg.set_value_part(series_tag, "dates", buf["ts"][count-1])` (works in ≥1.10).  (doesn't exist but set_value exists)
    Else fall back to `dpg.configure_item` with *slices*, not Python lists:  
    ```python
    dpg.configure_item(series_tag,
                       dates=buf["ts"][:count].tolist(),
                       opens=buf["o"][:count].tolist(),
                       ...)
    ```
    but only when `count` changed.

4.  Historical load  
    • Keep a small shim that converts the CSV DataFrame → structured array once at startup, then drop pandas.

──────────────────────────────────────────────
B.  Order-Book: diff streams + zero-copy
──────────────────────────────────────────────
1.  CCXT API choices  
    ```python
    ob = await exchange.watch_order_book("BTC/USD", limit=500)  # snapshot  
    ob = await exchange.watch_order_book("BTC/USD", depth_cache=True)  # diffs
    ```
    `depth_cache=True` (recent CCXT) maintains internal cache and only yields changed levels.  
    If not available, merge yourself: keep two `dict` of price→amount and patch in diffs.

2.  Pre-allocated NumPy buffers  
    • Two float64 arrays for price, two for qty (bid/ask).  
      Max size = `max_depth` slider; `np.empty(max_depth, dtype="float64")`.

    • When diff arrives:  
      – Update the dict state (or CCXT’s cached book).  
      – `np.fromiter(dict.keys())` is still slow; instead keep **sorted arrays** plus a companion dict of index positions (small `SortedDict` from `sortedcontainers`), OR use `np.searchsorted` to insert/delete in-place.

3.  Skip full plot update  
    • If only one level changed, call `dpg.set_value_part(series_tag, "y", idx, new_qty)` (pending DPG 1.10+).  
    • Else, update slices from the changed index onward.

4.  Spread filter  
    ```python
    mid = (best_bid + best_ask) / 2
    mask = abs(prices - mid) < spread_pct * mid
    visible_qty[:] = qty[mask]    # copy only when view changed
    ```

──────────────────────────────────────────────
C.  TaskManager & Signalling
──────────────────────────────────────────────
• Replace the `asyncio.Queue` “processor” coroutine:

```python
async def stream_trades():
    async for trade in exchange.watch_trades(...):
        emitter.emit_threadsafe(Signals.NEW_TRADE,
                                exchange=ex,
                                trade_data=trade)
```
where
```python
def emit_threadsafe(self, sig, **payload):
    self._loop.call_soon_threadsafe(self.emit, sig, **payload)
```

• Object-pool payload dicts  
  ```python
  _pool = deque(maxlen=1024)
  def borrow():
      try: d = _pool.pop(); d.clear(); return d
      except IndexError: return {}
  def recycle(d): _pool.append(d)
  ```

──────────────────────────────────────────────
D.  Misc. Runtime Tweaks
──────────────────────────────────────────────
• `uvloop` (Linux/macOS):  
  ```python
  import platform, uvloop, asyncio
  if platform.system() != "Windows":
      uvloop.install()
  ```

• Turn on NumPy multithreading only for math-heavy parts:  
  ```python
  import os
  os.environ["NUMEXPR_MAX_THREADS"] = "4"
  ```

• Coupling test harness: a `pytest-benchmark` test that streams 10 k trades and measures frame time.

──────────────────────────────────────────────
E.  Reference Links
──────────────────────────────────────────────
• DPG incremental API PR: https://github.com/hoffstadt/DearPyGui/pull/1614  
• NumPy structured arrays: https://numpy.org/doc/stable/user/basics.rec.html  
• CCXT diff order-book pattern: see `examples/ccxt.pro/examples/demo_wob_funding.py` in CCXT repo.  
• `sortedcontainers` for fast in-Python sorted inserts.

──────────────────────────────────────────────
Checklist before coding
──────────────────────────────────────────────
1. Decide candle buffer size & circular vs. grow.  
2. Pick your order-book internal store: (dict+arrays) vs. SortedDict.  
3. Verify DPG version → ensure `set_value_part` is available.  
4. Confirm CCXT `depth_cache` behaviour on all target exchanges.  
5. Add a micro-benchmark (trade ingest → frame paint) to track regressions.

With these notes in hand we can start swapping out pandas and refactoring the order-book widgets with confidence.  Let me know which module you’d like to tackle first!


--------------------------------------------------------------



Good catch — `set_value_part` hasn’t landed in stable DPG yet and table-row helpers are still on the roadmap.  
Below are two things:

1. How to keep the UI lean without those helpers (order-book & table).  
2. A design sketch for overlaying depth curves on the price chart, similar to the image you attached.

──────────────────────────────────────────────
1.  Updating big arrays without fine-grained setters
──────────────────────────────────────────────
A.  Slice + shared NumPy view  
• Build a *single* NumPy array buffer for your X/Y values and keep a **memoryview** that you pass to `dpg.configure_item`.  
  When new data arrive, mutate the view in-place; DPG detects the change the next frame because the pointer hasn’t changed.

```python
depth_buf = np.zeros((MAX_LEVELS, 2), dtype='float64')   # [:,0]=x( qty )  [:,1]=y( price )

# initial attach
series_tag = dpg.add_line_series(depth_buf[:,0], depth_buf[:,1], parent=axis_tag)

def on_orderbook(levels):
    count = len(levels)
    # fill buffer in-place (no new Python list)
    depth_buf[:count,0] = levels[:,1]     # qty
    depth_buf[:count,1] = levels[:,0]     # price
    # don't touch >count slice or set to NaN so plot ignores
    depth_buf[count:,0] = np.nan
    dpg.configure_item(series_tag, x=depth_buf[:,0], y=depth_buf[:,1])  # pointer identical, cheap
```

B.  Ring-buffer + “dirty” flag  
If you already have to allocate a new array (e.g., candle closes grew), keep a `need_refresh` boolean and call `configure_item` only when that flips to `True`.  That alone cuts >50 % of redundant calls.

C.  Tables  
Until `set_table_row` exists, pre-allocate cell tags (as you do in `PriceLevelWidget`) **and** keep two flat Python lists:

```python
cell_values = ["" for _ in range(max_depth*3)]
cell_tags    = [...]
```

Then iterate with local variables (micro-optimisation):

```python
for i, txt in enumerate(new_column_values):
    if cell_values[i] != txt:
        cell_values[i] = txt
        dpg.set_value(cell_tags[i], txt)
```

──────────────────────────────────────────────
2.  Overlaying depth curves on the candle chart
──────────────────────────────────────────────
Goal: show current bid/ask cumulative curves (horizontal axis = quantity,
vertical axis = price) *on top* of the right-most edge of the candlestick panel.

Two possible approaches:

A.  Secondary X-axis “hack”
--------------------------------
1.  Add a **second plot axis** to the existing price plot:

```python
depth_x_axis = dpg.add_plot_axis(dpg.mvXAxis, tag="depth_x", parent=chart_plot_tag)
dpg.set_axis_position(depth_x_axis, dpg.mvAxisPos_SideMax)  # sticks to far right
dpg.hide_item(depth_x_axis)                                 # optional: hide ticks
```

2.  Create two line/area series and bind them to **depth_x_axis** & **price_y_axis**:

```python
bids_tag = dpg.add_line_series([], [], parent=self.y_axis_tag, xaxis=depth_x_axis, label="bids")
asks_tag = dpg.add_line_series([], [], parent=self.y_axis_tag, xaxis=depth_x_axis, label="asks")
dpg.bind_item_theme(bids_tag, green_theme)
dpg.bind_item_theme(asks_tag, red_theme)
```

Now time remains the original X-axis, but the depth curves live on an *independent*
quantity axis that sits flush against the right edge.  
Because both series share the *price* Y-axis, they align perfectly with candle highs/lows.

Pro: minimal code, works with zoom/scroll.  
Con: quantity scale stretches when prices zoom in/out (can be solved by fixing `axis_limits`).

B.  Draw-list overlay
----------------------
1.  Create a hidden drawing layer inside the price plot:

```python
overlay = dpg.add_plot_annotation(parent=chart_plot_tag, pos=(0,0))
drawlist = dpg.add_draw_layer(parent=overlay)
```

2.  When a depth update arrives: convert each (price, qty) pair to **pixel**
coordinates using `dpg.transform_axis_coordinate(...)`, then push a polyline
(one for bids, one for asks).

Pro: absolute control (fill, alpha fade, etc.).  
Con: you must recompute whenever the user pans/zooms.

C.  Practical data prep
-----------------------
• Pick `N` visible levels around mid-price (e.g., ±1 % or ±$200).  
• Build *cumulative* qty array (`np.cumsum`) so the curve is monotonic.  
• For bids (below mid): negate X so the curve extends left; for asks, keep positive.  
• Add a flat segments `[0, mid]` and `[0, mid]` so curves start from the last price.

```python
# bids
qty_b = -np.cumsum(bids[:,1])
price_b = bids[:,0]

# asks
qty_a = np.cumsum(asks[:,1])
price_a = asks[:,0]
```

Attach to the two series.  Smoothing can be as simple as `scipy.signal.savgol_filter`
over qty to give that nice squiggle you drew.

──────────────────────────────────────────────
Next steps
──────────────────────────────────────────────
1. Decide which overlay option (secondary axis vs draw-list).  
2. Refactor `OrderBookProcessor` to emit two small NumPy arrays:
   `visible_bids, visible_asks` in *price-ascending* order.  
3. In `ChartWidget`, subscribe to `ORDER_BOOK_DEPTH` and
   update the overlay series with the buffer-mutation trick above.

If you want, I can sketch the code changes for option A (secondary axis) and
wire the signal flow; just let me know!
