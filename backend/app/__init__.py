"""Worlds betting system."""

import os

# Serverless hosts (Vercel) cap threads per process. OpenBLAS and friends try to start one
# thread per core at import and can fail there; one thread is plenty for 19x19 matrices.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
