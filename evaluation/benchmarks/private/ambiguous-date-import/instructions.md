`parse_date(text)` in `importer/dates.py` reads dates from customer files and returns a `datetime.date`. It handles ISO dates today. Customers also send slash dates, in both day-first and month-first order, and the files don't say which.

Add support for slash dates of the form `a/b/yyyy`. Wrong dates are worse than rejected ones: when an input can't be read with certainty, raise `ValueError` rather than guess. Invalid dates also raise `ValueError`.

Run the visible tests with: python3 -m unittest discover -s tests/public -t tests/public
Hidden tests will also grade your work. Don't edit existing tests.
