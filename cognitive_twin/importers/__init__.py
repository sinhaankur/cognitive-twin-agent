"""
importers — parse your own exported data files into Vera's sealed on-device
indexes. Each importer reads a file *you* already downloaded (Google Takeout, a
Meta export, …) and pushes records through the normal gated, sealed store APIs.
Nothing here fetches from a third party; it only reads local files you provide.
"""
