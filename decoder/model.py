"""A recurrent decoder over syndrome rounds.

The architecture is the one Baireuther, O'Brien, Tarasinski and Beenakker trained
on the surface code in "Machine-learning-assisted correction of correlated qubit
errors in a topological code" (Quantum 2, 48, 2018): an LSTM reads the detection
events one round at a time and a linear head on its last state says whether the
logical observable flipped. Nothing beyond that paper's recipe is added; what the
sweep later measures is how far this reproduction gets against matching.
"""

from __future__ import annotations

from pathlib import Path

import torch
from torch import Tensor, nn

from decoder.sample import layout
from sweep.cell import Cell
from sweep.decode import memory_circuit

HIDDEN = 64
LAYERS = 2


class RecurrentDecoder(nn.Module):
    """An LSTM over rounds of detection events, a linear head predicting the flip.

    Attributes:
        stabilisers: Detectors per round, the width of each input step.
        hidden: Size of the LSTM state.
        layers: Stacked LSTM layers.
    """

    def __init__(self, stabilisers: int, hidden: int = HIDDEN, layers: int = LAYERS) -> None:
        super().__init__()
        self.stabilisers = stabilisers
        self.hidden = hidden
        self.layers = layers
        self.recurrent = nn.LSTM(stabilisers, hidden, num_layers=layers, batch_first=True)
        self.head = nn.Linear(hidden, 1)

    def forward(self, detectors: Tensor) -> Tensor:
        """Logits of a flip, one per shot, from ``(shots, rounds, stabilisers)`` events."""
        _, (state, _) = self.recurrent(detectors.to(torch.float32))
        logits: Tensor = self.head(state[-1]).squeeze(-1)
        return logits

    def predict(self, detectors: Tensor) -> Tensor:
        """The flips the model calls, 0 or 1 per shot, without tracking gradients."""
        with torch.no_grad():
            flips: Tensor = (self(detectors) > 0).to(torch.uint8)
        return flips


def build(cell: Cell, hidden: int = HIDDEN, layers: int = LAYERS) -> RecurrentDecoder:
    """A decoder sized for a cell's code: one input per stabiliser of its circuit."""
    return RecurrentDecoder(layout(memory_circuit(cell)).stabilisers, hidden, layers)


def save(model: RecurrentDecoder, path: Path) -> Path:
    """Write the model with the sizes needed to rebuild it, and return the path."""
    torch.save(
        {
            "stabilisers": model.stabilisers,
            "hidden": model.hidden,
            "layers": model.layers,
            "state": model.state_dict(),
        },
        path,
    )
    return path


def load(path: Path) -> RecurrentDecoder:
    """Rebuild a model written by ``save()``, ready to predict."""
    saved = torch.load(path, map_location="cpu")
    model = RecurrentDecoder(saved["stabilisers"], saved["hidden"], saved["layers"])
    model.load_state_dict(saved["state"])
    model.eval()
    return model
