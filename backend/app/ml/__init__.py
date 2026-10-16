"""Learned theme classifier (see experiment notes in docs/review).

labels.py and registry.py are plain Python and safe to import from the web app.
features.py, train.py and infer.py import numpy / scipy / scikit-learn: only the CLI uses
them, and the scheduler runs that CLI in a child process so the memory goes back afterwards."""
