"""
Final: LangChain + Gemini structured JSON with template + temp bump retry

Requires:
  pip install -U langchain langchain-core langchain-google-genai pydantic

Env:
  export GOOGLE_API_KEY=...
"""

from typing import Type, Dict, Any
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI


class Response(BaseModel):
    files_for_editing: list[str] = Field(default_factory=list, description="files for editing")


# -----------------------------
# 2) Core runner
# -----------------------------
def run_structured(
    prompt: ChatPromptTemplate,
    variables: Dict[str, Any],
    schema: Type[BaseModel],
    model_name: str = "gemini-2.5-flash",
) -> Dict[str, Any]:
    """
    Render `prompt` with `variables`, call Gemini through LangChain with structured output,
    first at temperature=0.0. If that fails (e.g., validation/transport error), retry at 0.7.

    Returns a Python dict (valid JSON).
    Raises the last exception if both attempts fail.
    """
    # Attempt 1: temp=0.0
    llm_cold = ChatGoogleGenerativeAI(model=model_name, temperature=0.0)
    structured_cold = llm_cold.with_structured_output(schema)

    try:
        result_obj: BaseModel = (prompt | structured_cold).invoke(variables)
        return result_obj.model_dump()
    except Exception as first_err:
        # Attempt 2: temp=0.7
        llm_warm = ChatGoogleGenerativeAI(model=model_name, temperature=0.7)
        structured_warm = llm_warm.with_structured_output(schema)
        try:
            result_obj: BaseModel = (prompt | structured_warm).invoke(variables)
            return result_obj.model_dump()
        except Exception as second_err:
            # Re-raise the warm error, but keep original context
            raise RuntimeError(
                f"Structured generation failed (0.0 then 0.7). "
                f"First error: {first_err}\nSecond error: {second_err}"
            )


# -----------------------------
# 3) Example usage
# -----------------------------
if __name__ == "__main__":
    # You bring your own ChatPromptTemplate:
    system_msg = (
        "You are a precise planner. "
        "Always adhere exactly to the provided schema. "
        "If info is missing, use reasonable defaults that keep the schema valid."
    )
    user_template = (
        "TASK:\n{task}\n\n"
        "CONTEXT:\n{context}\n\n"
        "CONSTRAINTS:\n{constraints}"
    )
    from langchain_core.prompts import PromptTemplate
    PromptTemplate.from_template
    prompt = ChatPromptTemplate.from_messages(
        [("system", system_msg), ("user", user_template)]
    )

    inputs = {
        "task": "Plan a home office setup",
        "context": "- Budget: $800\n- Space: small corner\n- Must include ergonomic chair",
        "constraints": "- Quiet peripherals\n- Max desk width 120cm",
    }

    plan_dict = run_structured(prompt, inputs, TaskPlan)
    print(plan_dict)  # <-- strict JSON (Python dict)
