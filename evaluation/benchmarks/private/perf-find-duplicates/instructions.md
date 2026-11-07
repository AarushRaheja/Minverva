`find_duplicates(items)` in `dedupe/core.py` is too slow on large inputs, because it does far too many comparisons. Make it run in linear time without changing what it returns: each value that appears more than once, one time each, in the order its second occurrence was seen. Items are hashable.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.
