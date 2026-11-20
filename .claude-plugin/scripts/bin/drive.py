#!/usr/bin/env python3
"""Shebang wrapper for drive. No logic; see livespec_orchestrator_beads_fabro.commands.drive."""

from _bootstrap import bootstrap

# A direct drive can inherit the retired host-default App even though the
# target repository declares its owning App in its credential wrapper. Always
# take that target projection once before importing the command router.
bootstrap(force_credential_wrapper=True)

from livespec_orchestrator_beads_fabro.commands.drive import main

raise SystemExit(main())
