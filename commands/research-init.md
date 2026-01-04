---
description: Initialize a new research problem for algorithm discovery
---

# Initialize Research Problem

Run the obsidian research init command to set up a new algorithm discovery problem:

```bash
obsidian research init --template $ARGUMENTS
```

If no template is specified, use "algorithm" as the default template.

Available templates:
- algorithm: For sorting, search, graph algorithms
- ml_model: For neural network design
- optimization: For mathematical optimization
- custom: For user-defined problems

After initialization, explain the created files and what the user should do next.
