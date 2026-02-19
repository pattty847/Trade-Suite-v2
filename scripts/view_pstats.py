import pstats
from pstats import SortKey

# Load the profiling data
p = pstats.Stats('logs\\yappi_20250504_163046.pstat')

# Remove leading path information from filenames
p.strip_dirs()

# Sort the statistics by cumulative time spent in the function
p.sort_stats(SortKey.CUMULATIVE)

print("Top 10 functions by cumulative time:")
p.print_stats(10)

print("\nTop 10 functions by total time spent in the function itself (not including sub-calls):")
p.sort_stats(SortKey.TIME)
p.print_stats(10)

print("\nCallers of a specific function (example: if you have a function named 'my_function'):")
# p.print_callers(.1, 'my_function') # Show callers contributing to 10% of time for 'my_function'

print("\nCallees of a specific function (example: if you have a function named 'my_function'):")
# p.print_callees(.1, 'my_function') # Show callees called by 'my_function' that contribute to 10% of its time 