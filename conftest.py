"""Settings for every test run.

One thread each for the numerical libraries.  pytest-xdist runs several
workers, and each would otherwise start a thread per core: on a four-core
machine, four workers ran 3.3 times slower that way (213 s against 64 s).
The libraries read them when they load.  A pytest plugin has already
loaded numpy in this process by the time this file runs, so a run without
workers keeps the default; the workers start afterwards and inherit them.
"""

import os

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")
