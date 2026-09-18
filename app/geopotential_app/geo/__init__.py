"""Display-only geodesy. ADR-MSP-003.

Reprojecting the *data* is a run in the worker, with a manifest. Reprojecting
what is *shown* happens here, is reachable only from the drawing and reporting
paths, and changes nothing that is stored.
"""
