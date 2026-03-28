#!/usr/bin/env python3
from agent import Agent
from tools import TOOLS

import sys
sys.argv[1:1] = ["claude-sonnet-4.6", "--provider", "bankr"]
Agent(extra_tools=TOOLS, max_iterations=30).cli()
