Add `export_csv(path, include_retired=False)` to `stock/items.py`. It writes a CSV with the header `sku,name,quantity`, one row per item sorted by sku, and returns the number of rows written. Retired items are left out unless include_retired is true. Names may contain commas and quotes, so the output must be valid CSV.

`add_item` and `list_items` must keep working exactly as they do now for existing callers.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.
