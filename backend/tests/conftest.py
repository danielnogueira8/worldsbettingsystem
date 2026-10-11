import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="wbs-test-")
os.environ["WBS_DATA_DIR"] = _tmp
os.environ["WBS_DB_URL"] = f"sqlite:///{_tmp}/test.sqlite"
os.environ["WBS_N_SIMS"] = "2000"
