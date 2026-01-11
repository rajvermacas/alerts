Right now there is a tool named #src/alerts/agents/insider_trading/agent.py#142 AlertReaderTool which i want to delete. 
Because currently the orchestrator accepts the payload with alert xml and then it passes to insider trading agent and then insider trading agent has a tool to read the xml using LLM and find important contextual data to pass onto to other tools.

The change i want is to pass the important contextual data from the big data layer itself which in our case happens to be the UI i think because the big data layer sits with another team so we just need to provide the api contract to them. 

Once only the contextual alert data is passed to the whole agentic system I don't think there is any requirement to have a separate alertreadertool.