import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.api import app
from app import jobs


class APITests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_exposes_only_presence_and_nvidia_provider(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'private-value', 'TAVILY_API_KEY': ''}):
            response = self.client.get('/api/health')
        self.assertNotIn('private-value', response.text)
        self.assertEqual(response.json().get('provider'), 'nvidia')
        self.assertIs(response.json().get('nvidia_key'), True)
        self.assertNotIn('groq_key', response.json())

    def test_missing_provider_key_rejected_before_creating_work(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': ''}), patch('app.jobs.create_job') as create:
            response = self.client.post('/api/auto/start', json={'topic':'AI'})
        self.assertEqual(response.status_code, 503)
        create.assert_not_called()

    def test_whitespace_feedback_does_not_resume_graph(self):
        with patch('app.api.app_hitl.invoke') as invoke:
            response = self.client.post('/api/hitl/resume', json={'thread_id':'id','feedback':'   '})
        self.assertEqual(response.status_code, 422)
        invoke.assert_not_called()

    def test_unexpected_graph_exception_is_redacted(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'test'}), patch('app.api.app_hitl.invoke', side_effect=RuntimeError('secret-from-provider')):
            response = self.client.post('/api/hitl/start', json={'topic':'AI'})
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('secret-from-provider', response.text)

    def test_hitl_draft_and_approval_use_same_graph_without_second_write(self):
        with patch.dict(os.environ, {'NVIDIA_API_KEY': 'test'}), patch('app.writer._get_writer_llm') as get:
            get.return_value.invoke.return_value = AIMessage(content='A useful post.')
            response = self.client.post('/api/hitl/start', json={'topic':'AI'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['status'], 'awaiting_review')
            approved = self.client.post('/api/hitl/resume', json={'thread_id':response.json()['thread_id'],'feedback':'approved'})
        self.assertEqual(approved.status_code, 200)
        self.assertTrue(approved.json()['is_approved'])
        get.return_value.invoke.assert_called_once()

    def test_autonomous_failure_keeps_draft(self):
        from app.runner import run_auto_job
        job = jobs.create_job('AI', False)
        chunks = [{'prepare_attempt': {'attempt':1}}, {'extract_draft': {'draft':'Saved post'}},
                  {'reviewer': {'error':'Quota reached', 'error_status':429}}]
        with patch('app.runner.app_auto.stream', return_value=iter(chunks)):
            run_auto_job(job, 'AI', False)
        result = self.client.get(f'/api/auto/status/{job}').json()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['draft'], 'Saved post')
        self.assertEqual(result.get('error_status'), 429)


if __name__ == '__main__':
    unittest.main()
