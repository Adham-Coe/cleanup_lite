Cleanup Lite is a lightweight disk cleanup utility written in Python with a user-friendly tabbed interface.
It helps free up disk space by scanning for large/unnecessary files while keeping system performance in mind.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Overview:

Cleanup Lite is designed to be simple yet powerful. It scans your system for unnecessary files, presents them in a clean UI,
 and allows you to safely delete them. It’s built with Tkinter (Python’s GUI library) and supports tabbed navigation for different features.
The tool balances usability and efficiency: it handles files in memory-friendly chunks, filters results dynamically,
 and even includes a fun mini-game tab for breaks while cleaning!
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Features:

1. File Scanner – Scans selected folders for files larger than a user-defined size threshold.
2. Results Viewer – Displays results in a table with file name, size, and location for review.
3. Cleanup Action – Lets users safely delete unwanted files from inside the app.
4. Mini-game Tab – A small interactive “throw crumpled paper into basket” game for fun while cleaning.
5. Light and Dark Modes - The user can change the theme color between dark and light.
6. Scan Progress Bar - Allows the user to track scanning progress.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Major Complex Feature:

Generator-based Scanning with Chunked File Handling
* Instead of loading all files into memory at once, Cleanup Lite uses a generator-based file scanner.
* Files are yielded one by one in chunks, preventing the program from freezing and keeping RAM usage low during large scans.
* This also allows the UI to update dynamically while scanning.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Memory Optimization Methods:

Cleanup Lite integrates two genuine optimization methods:
1. Generator-based File Iteration
* Scanning is implemented with Python generators (yield), which load only one file’s metadata at a time.
* This reduces peak memory consumption drastically compared to list-based scans.

2. Chunked File Handling
* File I/O operations are handled in manageable chunks instead of reading whole files into memory.
* Prevents memory spikes and ensures smooth performance on large files.
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Usage:

1. Open the included Main.exe file.
2. Choose a folder to scan.
3. Review the listed files.
4. Delete selected files if needed.
5. Try the Mini-game tab if the scan takes so long!
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------
License:

Licensed under the MIT License (free to use, modify, distribute).