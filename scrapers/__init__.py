"""Registry: provider key in config.yaml → site module. Add a new site = new module + one line here."""
from . import bls, vfs

SITES = {
    vfs.PROVIDER: vfs,
    bls.PROVIDER: bls,
}
