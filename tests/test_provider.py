"""Offline regressions. Run with PYTHON_DOTENV_DISABLED=1; never read real .env."""
import os
import unittest
from unittest.mock import MagicMock, patch

from app import config


class ProviderTests(unittest.TestCase):
    def test_nvidia_configuration_is_used(self):
        self.assertEqual(getattr(config, 'NVIDIA_KEY_NAME', None), 'NVIDIA_API_KEY')
        self.assertEqual(config.WRITER_MODEL, 'nvidia/nemotron-3.5-lightning-30b-a3b')
        from app import llm
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'test-placeholder'}), patch('app.llm.ChatNVIDIA') as model:
            llm.make_writer_llm()
            llm.make_reviewer_llm()
        self.assertEqual(model.call_count, 2)
        for call in model.call_args_list:
            self.assertEqual(call.kwargs['base_url'], 'https://integrate.api.nvidia.com/v1')
            self.assertLessEqual(call.kwargs['max_completion_tokens'], 2048)
            self.assertEqual(call.kwargs['timeout'], 45)
            self.assertEqual(call.kwargs['model_kwargs']['chat_template_kwargs']['enable_thinking'], False)
            self.assertEqual(call.kwargs['model_kwargs']['tool_choice'], 'none')

    def test_real_nvidia_factories_and_bindings_are_offline(self):
        from app import reviewer
        from app.llm import make_writer_llm
        with patch.dict(os.environ, {'NVIDIA_API_KEY':'test-placeholder'}), patch('requests.Session.request', side_effect=AssertionError('Unexpected network request')):
            writer = make_writer_llm()
            writer.bind_tools([reviewer.ReviewVerdict], tool_choice='auto')
            with patch.object(reviewer, '_reviewer_llm', None), patch.object(reviewer, '_structured_reviewer', None):
                plain, structured = reviewer._get_reviewers()
                self.assertIsNotNone(structured)
                self.assertEqual(plain.model, 'nvidia/nemotron-3.5-lightning-30b-a3b')

    def test_real_structured_reviewer_parses_one_mocked_http_call(self):
        import json
        from requests import Response
        from app import reviewer
        response = Response()
        response.status_code = 200
        response._content = json.dumps({'choices':[{'index':0,'message':{'role':'assistant','content':'',
            'tool_calls':[{'id':'verdict1','type':'function','function':{'name':'ReviewVerdict',
            'arguments':json.dumps({'approved':True,'feedback':'Clear and specific.'})}}]},
            'finish_reason':'tool_calls'}]}).encode()
        with patch.dict(os.environ, {'NVIDIA_API_KEY':'test-placeholder'}), patch('requests.Session.request', return_value=response) as request:
            with patch.object(reviewer, '_reviewer_llm', None), patch.object(reviewer, '_structured_reviewer', None), patch.object(reviewer, '_structured_output_broken', False):
                result = reviewer._review_with_fallback('A useful draft')
        self.assertTrue(result.approved)
        self.assertEqual(request.call_count, 1)
        self.assertIn('integrate.api.nvidia.com', str(request.call_args))

    def test_missing_key_is_actionable(self):
        self.assertTrue(hasattr(config, 'require_nvidia_key'))
        with patch.dict(os.environ, {'NVIDIA_API_KEY': ''}):
            with self.assertRaisesRegex(RuntimeError, 'NVIDIA_API_KEY'):
                config.require_nvidia_key()

    def test_quota_errors_are_not_retried_or_exposed(self):
        from app.llm import LLMError, invoke_with_retry
        runnable = MagicMock()
        runnable.invoke.side_effect = Exception('[429] private-key-or-prompt')
        with patch('app.llm.time.sleep') as sleep:
            with self.assertRaises(LLMError) as caught:
                invoke_with_retry(runnable, [], what='writer')
        self.assertEqual(runnable.invoke.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(caught.exception.status_code, 429)
        self.assertNotIn('private-key', str(caught.exception))

    def test_permanent_errors_do_not_retry(self):
        from app.llm import LLMError, invoke_with_retry
        for code in (400, 401, 403, 404, 410, 422):
            runnable = MagicMock()
            runnable.invoke.side_effect = Exception(f'[{code}] private')
            with self.subTest(code=code), patch('app.llm.time.sleep') as sleep:
                with self.assertRaises(LLMError):
                    invoke_with_retry(runnable, [], what='writer')
                self.assertEqual(runnable.invoke.call_count, 1)
                sleep.assert_not_called()

    def test_transient_server_failure_has_one_bounded_retry(self):
        from app.llm import invoke_with_retry
        runnable = MagicMock()
        runnable.invoke.side_effect = [Exception('[503] private'), 'recovered']
        with patch('app.llm.time.sleep') as sleep:
            self.assertEqual(invoke_with_retry(runnable, [], what='writer'), 'recovered')
        self.assertEqual(runnable.invoke.call_count, 2)
        sleep.assert_called_once()

    def test_review_quota_failure_does_not_trigger_fallback(self):
        from app import reviewer
        from app.llm import LLMError
        plain, structured = MagicMock(), MagicMock()
        structured.invoke.side_effect = LLMError('Quota reached', status_code=429)
        with patch('app.reviewer._get_reviewers', return_value=(plain, structured)), patch.object(reviewer, '_structured_output_broken', False):
            with self.assertRaises(LLMError):
                reviewer._review_with_fallback('draft')
        plain.invoke.assert_not_called()

    def test_review_schema_failure_can_fall_back(self):
        from app import reviewer
        plain, structured = MagicMock(), MagicMock()
        structured.invoke.side_effect = ValueError('Unsupported structured response')
        plain.invoke.return_value.content = 'VERDICT: REJECTED\nFEEDBACK: Be specific.'
        with patch('app.reviewer._get_reviewers', return_value=(plain, structured)), patch.object(reviewer, '_structured_output_broken', False):
            result = reviewer._review_with_fallback('draft')
        self.assertFalse(result.approved)
        self.assertEqual(result.feedback, 'Be specific.')


if __name__ == '__main__':
    unittest.main()
