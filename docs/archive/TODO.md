Alright, here’s the straight‑shot review.

---

## 1. Top‑level flow

```
__main__  →  Data / ConfigManager / InfluxDB
          →  Viewport(...)
          →  with Viewport as vp:
                 vp.start_program()
```

At a glance that’s sensible: one object owns the GUI lifecycle and receives already‑wired dependencies.  Where it starts to wobble is **who really owns what** once things spin up:

* **TaskManager** creates its *own* event loop on another thread and never stops it unless `Viewport.__exit__` runs cleanly. If the app crashes inside DPG, that thread survives. A daemon thread hides the leak but doesn’t fix it. citeturn0file0  
* **SECDataFetcher** and anything DB‑related are also handed to Viewport, but Viewport never propagates shutdown signals to the widgets that might still be subscribed when `dpg.destroy_context()` is called. You risk dangling asyncio tasks that keep ccxt websockets open.

---

## 2. TaskManager

### Concurrency model
* One thread → its own asyncio loop.  
* UI thread → DearPyGUI loop.  
* Messages cross the boundary through `asyncio.Queue` + `SignalEmitter`.

That’s fine in theory, but several details bite:

| Issue | Impact | Fix / Question |
|-------|--------|----------------|
| `stop_task` calls `.cancel()` on a **concurrent.futures.Future** returned by `run_coroutine_threadsafe`; cancellation on those objects *does not* propagate unless the coroutine awaits a `CancelledError`. You think you cancelled but the stream may still run. citeturn0file0 | Memory/socket leaks, latent exceptions in background thread. | Keep a handle to the underlying `asyncio.Task` (you can get it via `asyncio.run_coroutine_threadsafe(...).result()` pattern) or add an explicit “should_run” flag checked inside every stream loop. |
| Every DPG callback ultimately touches `TaskManager.subscribe()` which acquires `self.lock`, then may kick off `_fetch_initial_candles_for_factory()` that awaits network IO **still while you’re on the UI thread** (because you immediately `run_coroutine_threadsafe`). Worst‑case: UI freezes if thread pool is saturated or queue blocks. | Janky UI under load. | Defer the heavy call entirely to the TaskManager loop; from the UI thread just enqueue a message telling the loop to start a fetch. |
| Reference counts mix str keys (`trades_…`) and tuple keys `(exch, sym, tf)`. A typo in one place leaves orphan factories. | Ghost factories, missed unsubscribes. | Wrap keys in small dataclass/enum objects so the type system enforces consistency. |

### Architectural smell
`TaskManager` is both a *subscription registry*, a *factory cache* **and** a *stream supervisor*.  That makes unit‑testing painful.  Split it:

1. **StreamSupervisor** – owns event loop & lifecycle of raw streams.  
2. **CandleFactoryCache** – pure synchronous cache living in UI thread.  
3. **SubscriptionBroker** – translates widget requirements into (2) and (1).

---

## 3. Dashboard layer

`DashboardProgram` and `DashboardManager` do the right thing by pushing layout concerns down into one class.  A few flags:

* **Widget instantiation** duplicates symbol/timeframe validation logic that already lives in your Data layer.  DRY it up by exposing a `Data.get_default_symbol(exchange)` and reuse it everywhere. citeturn0file1
* `DashboardManager.initialize_layout()` toggles DPG’s `init_file` twice (once to load, then again to redirect saves). That’s clever but fragile; a future DPG version might cache the value only on first call. Keep a single source of truth inside `DashboardManager` and call `dpg.configure_app` once. citeturn0file1

---

## 4. Viewport bootstrap

You correctly call `load_exchanges()` *before* `dpg.create_context()`.  Good.  But then:

```python
while dpg.is_dearpygui_running():
    self.data.emitter.process_signal_queue()
    dpg.render_dearpygui_frame()
```

If `process_signal_queue()` raises, you swallow it and the loop continues with undefined state. Wrap each iteration in a try/except or—better—make `SignalEmitter` fail‑safe. citeturn0file2

---

## 5. What’s missing for a deeper review

I can’t fully judge the data flow or memory profile without:

1. **Data** – especially `watch_trades`, `watch_orderbook`, `fetch_candles`.
2. **SignalEmitter** – queue implementation, thread‑safety guarantees.
3. **CandleFactory** – how it turns trades into candles; whether it back‑fills gaps; strategy for daylight‑saving, exchange outages, etc.
4. **Widget base class** – to see how `create()` and `close()` handle resubscription.
5. **InfluxDB layer** – write batching, retry logic, off‑thread commits.

Send those next and we can dig into:

* back‑pressure & rate‑limit handling,
* proper shutdown semantics,
* testability seams, and
* how to evolve toward a plug‑in architecture so widgets can register their own data needs without touching TaskManager internals.

---

### Immediate action items

1. **Cancellation audit** – prove with a unit test that unsubscribing a widget truly stops the ccxt websocket.  
2. **Thread‑safe handoff** – move *all* network‑bound set‑ups off the UI thread.  
3. **Split concerns** – carve TaskManager into the three roles above; your cognitive load will drop and tests get simpler.  
4. **Add a watchdog** – log a warning if any asyncio task runs > N seconds without yielding; that’ll surface hung coroutines early.

Tackle these, then we’ll go a layer deeper.


----------------

Good—let’s zoom in on these five pieces and surface the structural cracks before you paper‑maché more features onto them.

---

## 1 · `SignalEmitter` – the aorta of the app  
**Current state**

* Dict of lists holds strong references to bound methods. Whatever registers will never be garbage‑collected until you manually `unregister`. citeturn1file3  
* No lock around `_callbacks`; registering from the DPG thread while CandleFactory registers from the TaskManager thread is a race you simply haven’t hit yet.
* A queue with unbounded growth and no back‑pressure. If the UI thread lags, the background loop will happily dump tens of thousands of events in seconds.

**Tighten it**

| Fix | Why it matters |
|-----|----------------|
| Wrap callbacks in `weakref.WeakMethod` (or `weakref.ref` for functions) so GC can clean up on widget close. | Prevents hidden leaks when widgets are destroyed but forget to unregister. |
| Guard `_callbacks` mutations with `threading.RLock`. | Safe in the face of concurrent subscription/unsubscription. |
| Add `maxsize` to the queue and drop or coalesce low‑priority events when full. | Stops memory explosions during network hiccups. |

---

## 2 · `CandleFactory` – data engine  
* You call `self.emitter.register(Signals.NEW_TRADE, self._on_new_trade)` and rely on `TaskManager.unsubscribe()` to `unregister`. Good—**but** if a factory is orphaned because a ref‑count bug skips `unsubscribe`, that strong reference cycle lives forever.  citeturn1file2  
* Price/volume math runs inside the **SignalEmitter main thread callback** (UI thread) because `_on_new_trade` fires there. That defeats the whole “background processing” goal.  
  *Move the heavy lifting to the TaskManager loop and emit only finished‐candle updates to the UI.*

* `_process_trade_batch()` rebuilds the last BAR on *every* trade batch, then emits the entire last row. Charts redraw even if nothing actually changed (e.g. a trade inside the candle’s body). Compare previous OHLCV hash before emitting to save frames.

---

## 3 · `ChartWidget` – God‑object smell  
The class plays four roles: view, controller, indicator calculator, and partially a model (it owns `self.ohlcv`). That’s why it’s ~800 lines.  citeturn1file1

**Refactor direction**

1. **Model (`SeriesCache`)** – plain‑data holder with min/max, last candle, EMA cache.  
2. **Service (`ChartController`)** – listens to signals, mutates the model, decides when to redraw.  
3. **View (`ChartWidget`)** – thin dpg wrapper; knows tags and nothing else.  

You’ll gain testability (unit‑test controller without DPG) and frame‑rate (model updates can happen off‑thread, then you post a single “render” message).

---

## 4 · `DockableWidget` – lifecycle & DPG integration  
* DPG 1.11 dropped the `on_close` kwarg; relying on it will break your next library upgrade. Consider subscribing to `mvEvent_DragPayload` + window flags instead, or wrap a custom handler that intercepts `mvAppItemType::mvWindowAppItem::draw`. citeturn1file0  
* `task_manager.subscribe()` is invoked inside `create()`, **before** any child plot exists. If subscription immediately dumps `NEW_CANDLES`, your `_on_new_candles` will try to configure a plot that isn’t created yet. Race is rare but real—delay subscription until end of `register_handlers()` with a `dpg.set_frame_callback(1, lambda: …)`.

---

## 5 · `Data` / CCXT streams  
* Loops exit only when `self.is_running` flips. `TaskManager.stop_task()` cancels the *Future*—the coroutine catches `CancelledError`, but `Data.is_running` stays `True`, so another call to `watch_trades()` later on the same `Data` instance spawns **two** loops. Make `is_running` a per‑stream `asyncio.Event` or pass a `cancel_token` instead of a global flag. citeturn1file4  
* After every await you immediately `.emit()`. That’s okay, but include exponential back‑off when CCXT throws; right now you hammer the exchange if it’s down.

---

## Immediate upgrades to tackle

1. **Thread‑safe, leak‑free `SignalEmitter`** (weak refs + locks + back‑pressure).  
2. **Move CandleFactory trade digestion off the UI thread**; send only finished delta to widgets.  
3. **Split ChartWidget** into MVC pieces.  
4. **Rework cancellation semantics** so TaskManager doesn’t rely on dirty thread‑safe futures.  
5. **Unit‑test** unsubscribe ➜ ensure websocket truly closes.

---

### What to show me next

To verify the remaining arteries, I need to see:

* `CCXTInterface` – to confirm how you share CCXT clients and handle rate limits.  
* `MarketAggregator` – your stat calculations might belong in CandleFactory.  
* `InfluxDB` wrapper – I want to check batching and async contention.  
* Any “utils” you reuse for timeframe parsing / DPG helpers (to see if logic duplication can be killed).

Drop those files and we’ll keep peeling the onion.