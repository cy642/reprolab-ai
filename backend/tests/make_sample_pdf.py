"""Generate a public sample paper PDF used by the API tests."""

from pathlib import Path

import pymupdf

OUTPUT = Path(__file__).resolve().parent / "fixtures" / "sample_paper.pdf"

PAGE_ONE = """Graph Neural Networks for Molecular Property Prediction

Alice Zhang, Bob Li

Abstract
Molecular property prediction is a core task in drug discovery. We present a
message-passing graph neural network that learns from atom and bond features.
Our approach achieves strong results on three public benchmarks and improves
the average ROC-AUC over the baseline by 3.1 points.

Keywords: graph neural network, molecular property, drug discovery
"""

PAGE_TWO = """1 Introduction
Molecular graphs encode atoms as nodes and chemical bonds as edges. Prior work
relies on handcrafted fingerprints, which limit generalization.

2 Method
We build a message-passing GNN with three layers and a sum readout. Node
features include atomic number and degree. Edges encode bond type.

3 Experiments
We evaluate on BBBP and Tox21 with scaffold splits. The hidden dimension is
128 and dropout is 0.1. Models are trained for 100 epochs with Adam.
"""

PAGE_THREE = """4 Results and Discussion
The proposed model improves average ROC-AUC by 3.1 points over the GNN
baseline. Ablations show that the sum readout is important.

5 Limitations
The evaluation covers only classification datasets, and larger molecular
datasets remain untested.
"""


def build() -> None:
    document = pymupdf.open()
    for text in (PAGE_ONE, PAGE_TWO, PAGE_THREE):
        page = document.new_page()
        page.insert_textbox(
            pymupdf.Rect(56, 56, 539, 786),
            text,
            fontsize=11,
            fontname="helv",
        )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document.save(OUTPUT)
    document.close()
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    build()
