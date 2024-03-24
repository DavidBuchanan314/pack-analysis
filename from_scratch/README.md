"How hard could it be to parse SQLite from scratch?" I wondered.

This is not production-quality code, but it seems like the answer is "really not that hard!".

Since the table schemas are simple and fixed, we don't actually have to implement "SQL", just basic data parsing.

Comparatively, zstandard would take much more effort to implement from scratch, and nobody really thinks twice about using zstandard as part of a protocol or file format.
