#!/usr/bin/env python3
from agent import Agent
from agent.leftclaw import make_leftclaw_tools
from agent.bgipfs import BGIPFS_TOOLS
from tools import TOOLS

import sys
sys.argv[1:1] = ["claude-sonnet-4.6", "--provider", "bankr"]

LEFTCLAW = make_leftclaw_tools(service_type_id=7)
Agent(extra_tools=LEFTCLAW + BGIPFS_TOOLS + TOOLS, max_iterations=30).cli()
