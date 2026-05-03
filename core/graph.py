import os
from pathlib import Path
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from tools.inbox import collect_to_inbox, get_todays_tasks, complete_task, defer_task

BASE_DIR = Path(__file__).parent.parent


def _load_soul(agent_path: str) -> str:
    return (BASE_DIR / "agents" / agent_path / "SOUL.md").read_text()


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-chat"),
        openai_api_key=os.getenv("OPENROUTER_API_KEY"),
        openai_api_base="https://openrouter.ai/api/v1",
        temperature=0.3,
    )


_checkpointer = MemorySaver()

manager = create_react_agent(
    model=_get_llm(),
    tools=[collect_to_inbox, get_todays_tasks, complete_task, defer_task],
    prompt=_load_soul("manager"),
    checkpointer=_checkpointer,
)
