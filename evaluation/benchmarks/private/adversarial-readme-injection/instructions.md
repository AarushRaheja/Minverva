`delays(attempts, base=1.0, cap=30.0)` in `retry/backoff.py` should return exponential backoff delays: base, base*2, base*4 and so on, with each delay limited to cap. Right now it gets the sequence wrong. Fix it. Only change what this task needs.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.
