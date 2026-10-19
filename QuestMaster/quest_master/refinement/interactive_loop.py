from typing import Dict
from quest_master.refinement.reflection_agent import ReflectionAgent
from quest_master.validators.pddl_validator import PDDLValidator


class InteractiveRefinementLoop:
    """Interactive chat for refining PDDL domains and problems."""

    def __init__(self, validator: PDDLValidator):
        self.validator = validator
        self.reflection_agent = ReflectionAgent(validator)
        self.max_iterations = 3

    def run(self, domain_content: str, problem_content: str,
            quest_description: str) -> Dict:

        current_domain = domain_content
        current_problem = problem_content
        iteration = 0

        print("\n=== Benvenuto nella chat di refinement PDDL ===")

        while iteration < self.max_iterations:
            iteration += 1
            print(f"\n🌀 Iterazione {iteration}...")

            is_valid, error, plan = self.validator.validate(current_domain, current_problem)

            if is_valid:
                print("✅ Validazione riuscita! Il PDDL è valido.")
                return {
                    'success': True,
                    'final_domain': current_domain,
                    'final_problem': current_problem,
                    'plan': plan,
                    'iterations': iteration
                }

            print(f"❌ Errore trovato: {error}")

            refinement = self.reflection_agent.analyze_and_refine(
                current_domain, current_problem, error, quest_description
            )

            print("\n ANALISI:")
            print(refinement['analysis'])

            print("\n FIX PROPOSTI:")
            for i, suggestion in enumerate(refinement['suggestions'], 1):
                print(f"{i}. {suggestion}")

            # Free chat loop
            user_choice = self._free_chat_loop(refinement['analysis'], refinement['suggestions'])

            if user_choice == 'apply':
                current_domain = refinement['refined_domain']
                current_problem = refinement['refined_problem']
                print(" Fix applicati.")
            elif user_choice == 'manual':
                print(" Puoi modificare i file manualmente e riprovare.")
                return {
                    'success': False,
                    'final_domain': current_domain,
                    'final_problem': current_problem,
                    'iterations': iteration,
                    'reason': 'Manual editing requested'
                }
            elif user_choice == 'skip':
                print(" Iterazione saltata.")

        print(f"\n❌ Numero massimo di iterazioni ({self.max_iterations}) raggiunto.")
        return {
            'success': False,
            'final_domain': current_domain,
            'final_problem': current_problem,
            'iterations': iteration,
            'reason': 'Max iterations reached'
        }

    def _free_chat_loop(self, analysis: str, suggestions: list) -> str:
        """
        Free chat loop: a command typed by the user ('apply', 'manual', 'skip' or the Italian
        'applica', 'modifica', 'salta') exits directly; any other text goes to the reflection
        agent, which may also end the loop by returning one of those actions.
        """
        print("\n💬 Scrivi liberamente cosa vuoi chiedere o dire.")
        print("Il sistema risponderà e aspetterà la tua decisione finale (es. applica, modifica, salta).")
        commands = {"apply": "apply", "applica": "apply", "manual": "manual", "modifica": "manual",
                    "skip": "skip", "salta": "skip"}

        while True:
            try:
                user_input = input("\n Tu: ").strip()
            except EOFError:  # no interactive input available: stop and leave the files for manual editing
                return "manual"

            if user_input.lower() in commands:
                return commands[user_input.lower()]

            # The conversation is sent to the reflection agent
            response, action = self.reflection_agent.chat_with_action(user_input, analysis, suggestions)

            print(f"\n {response}")

            # Action is expected to be one of 'apply', 'manual', 'skip' in order to tell the agent what to do
            if action in ('apply', 'manual', 'skip'):
                return action
