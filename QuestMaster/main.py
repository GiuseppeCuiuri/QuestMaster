from quest_master.langgraph_workflow import run_flow
from pathlib import Path
import json

if __name__ == "__main__":
    # Predefined paths for the lore document and output directory
    lore_path = "lore_document.txt"
    output_path = Path("examples/output")

    # Execute the flow with the given lore document and output directory
    result = run_flow("lore_document.txt", "examples/output")

    # Print the result of the LangGraph flow
    print("✅ LangGraph flow completed.")

    # Manage the result based on its type
    if hasattr(result, 'success'):
        # Result is an object GraphState
        success = result.success
        iterations = result.iterations
        result_dict = result.__dict__
    else:
        # Result is a dictionary
        success = result.get('success', False)
        iterations = result.get('iterations', 0)
        result_dict = result

    print("Status:", "SUCCESS" if success else "FAILURE")
    print("Iterations:", iterations)

    # Save the final state to a JSON file
    output_path.mkdir(parents=True, exist_ok=True)
    with open(output_path / "final_state.json", "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, default=str)
