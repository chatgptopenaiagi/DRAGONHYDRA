"""Job handler dispatch composed separately from the unchanged queue/claim owner."""

class JobDispatcher:
    def __init__(self, *, import_public, export, explanation, local_explanation,
                 context_run, provider_run, check, require_claim, stop, forecast=None, evaluation=None):
        self.import_public, self.export = import_public, export
        self.explanation, self.local_explanation = explanation, local_explanation
        self.context_run, self.provider_run = context_run, provider_run
        self.check, self.require_claim, self.stop = check, require_claim, stop
        self.forecast, self.evaluation = forecast, evaluation

    def execute(self, job):
        kind, payload = job['kind'], job['payload']
        if kind in ('forecast', 'evaluation'):
            handler = self.forecast if kind == 'forecast' else self.evaluation
            if not callable(handler):
                raise ValueError('WORKFLOW_HANDLER_NOT_CONFIGURED')
            self.check(job['id'], job['attempts'])
            return handler(job)
        if kind == 'import_public':
            return self.import_public(job['id'], payload.get('mode', 'retained'), job['attempts'])
        if kind == 'explanation':
            return self.explanation(payload['match_id'])
        if kind == 'local_explanation':
            return self.local_explanation(payload['package'], lambda: self.check(job['id'], job['attempts']))
        if kind == 'statsbomb_context':
            def require_context_claim(db, job_id, claim):
                current = self.require_claim(db, job_id, claim)
                if self.stop.is_set():
                    from ..jobs import Interrupted
                    raise Interrupted()
                return current
            return self.context_run(job, lambda: self.check(job['id'], job['attempts']), require_context_claim)
        if kind == 'export':
            return self.export(job)
        if kind in ('connector_test', 'connector_sync'):
            return self.provider_run(payload['provider'], 'sync' if kind == 'connector_sync' else 'test',
                                      lambda: self.check(job['id'], job['attempts']), job['id'])
        raise ValueError('UNSUPPORTED_JOB_KIND')

