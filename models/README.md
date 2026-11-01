# models

The decoder in force, as a manifest changed through a pull request.

`decoder.json` names the decoder, how a cell is decoded with it, the run that evaluated it and the image digest that run must have recorded. Changing the file is a pull request; the `models` workflow follows the candidate to its run in the bucket, refuses a manifest whose digest the run did not record, and compares the candidate with the decoder on `main` cell by cell, admitting it only if it is worse on no cell with the intervals apart and skipped none. Being better nowhere is allowed: a promotion can be for cost or for speed, as long as it loses no accuracy.

PyMatching is the first entry. A learned decoder lands the same way, with its weights' address and hash in the two fields the first entry leaves out.
