import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage
from app import writer
from app.state import initial_state


class WriterBudgetTests(unittest.TestCase):
    def test_tool_budget_resets_for_each_revision(self):
        state = initial_state('AI', True)
        state.update(attempt=1, tool_rounds=2, review_feedback='Make it specific.')
        update = writer.prepare_attempt_node(state)
        self.assertEqual(update.get('tool_rounds'), 0)

    def test_writer_stops_binding_tools_after_budget(self):
        state = initial_state('AI', True)
        state.update(tool_rounds=writer.MAX_TOOL_ROUNDS, messages=[HumanMessage(content='Write')])
        with patch('app.writer.tools.search_available', return_value=True), patch('app.writer._get_writer_llm') as get:
            get.return_value.invoke.return_value = AIMessage(content='Final post')
            result = writer.writer_node(state)
        get.assert_called_once_with(False)
        self.assertEqual(result['messages'][0].content, 'Final post')
        sent = get.return_value.invoke.call_args.args[0]
        self.assertIn('Search is now disabled', sent[-1].content)

    def test_tool_call_content_is_never_presented_as_a_finished_post(self):
        state = initial_state('AI')
        state['messages'] = [AIMessage(content='Searching now', tool_calls=[{'name':'search','args':{},'id':'call1'}])]
        self.assertIn('error', writer.extract_draft_node(state))

    def test_real_graph_finishes_after_tool_budget_on_each_revision(self):
        from langchain_core.tools import tool
        from app import graph_auto
        from unittest.mock import MagicMock

        @tool
        def lookup(query: str) -> str:
            """Return offline search context."""
            return "Relevant evidence."

        tool_model = MagicMock()
        counter = iter(range(10))
        tool_model.invoke.side_effect = lambda _: AIMessage(content='', tool_calls=[{
            'name':'lookup', 'args':{'query':'AI'}, 'id':f'call{next(counter)}'}])
        plain_model = MagicMock()
        plain_model.invoke.side_effect = lambda _: AIMessage(content='A completed post.')
        with patch('app.writer.tools.get_tools', return_value=[lookup]), patch('app.writer.tools.search_available', return_value=True), patch('app.writer._get_writer_llm', side_effect=lambda enabled: tool_model if enabled else plain_model), patch('app.graph_auto.reviewer_node', return_value={'is_approved':False,'review_feedback':'Be specific.'}), patch('app.config.MAX_ATTEMPTS', 2):
            graph = graph_auto.build_graph().compile()
            result = graph.invoke(initial_state('AI', True), config={'recursion_limit':60})
        self.assertIsNone(result.get('error'))
        self.assertEqual(result['attempt'], 2)
        self.assertEqual(result['draft'], 'A completed post.')
        self.assertEqual(tool_model.invoke.call_count, 4)
        self.assertEqual(plain_model.invoke.call_count, 2)


if __name__ == '__main__':
    unittest.main()
