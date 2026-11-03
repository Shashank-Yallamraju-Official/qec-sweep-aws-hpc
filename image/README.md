# image

The frozen environment. Three Apptainer definitions, each built by CI from a pinned base image by digest and a pinned package list, with the project as a wheel built outside the image, so two builds of one commit are the same and no build backend ever enters the image.

| Definition | Carries | Runs |
| --- | --- | --- |
| `sweep.def` | Stim, PyMatching, PyArrow | `sweep`, the cells; built for x86 and arm64 |
| `mpi.def` | the EFA libfabric and the nodes' Open MPI, mpi4py | `statevector`, one rank per core |
| `train.def` | the sweep image's pins plus torch's CPU build | `decoder-train`, and `sweep --decoder learned` |

## How it is built

The `image` workflow builds each on every pull request that touches its inputs, tags it with the commit, and checks the sweep image by rerunning a cell and comparing the count with the one recorded in `hand-built.json` from the node of stage 2. An image whose inputs did not change since the previous push is retagged rather than rebuilt. Stim and PyMatching publish no arm64 wheel, so the arm64 build compiles them from source and removes the toolchain afterwards.

## Where it fits

[`jobs/pull-image.sh`](../jobs/README.md) pulls an image once per digest; the baked AMI in [`cluster/`](../cluster/README.md) already carries main's latest. Test with `uv run pytest tests/image`.
