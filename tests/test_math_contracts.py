from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
import unittest

from dragonhydra.math.contracts import MathCapability, MathEngineRequest, MathEngineResult


class MathContractTests(unittest.TestCase):
    def setUp(self):
        self.request = MathEngineRequest(
            operation=MathCapability.PREDICT, inputs={"x": 1},
            input_fingerprint="synthetic-input-revision-1",
            target_as_of_at=datetime(2026, 9, 24, 12, tzinfo=timezone.utc), seed=42,
        )
        self.result = MathEngineResult(
            engine_id="synthetic-contract-only", engine_version="0", inputs={"x": 1},
            result=1, distribution=None, confidence=None, numerical_precision="float64",
            warnings=(), assumptions=("synthetic",), runtime=0, hardware="cpu",
            reason_codes=("CONTRACT_EXAMPLE",),
        )

    def test_unknown_confidence_is_explicit(self):
        self.assertIsNone(self.result.confidence)

    def test_invalid_confidence_rejected(self):
        for value in [-0.1, 1.1, float("nan"), float("inf"), True, "0.5"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.result, confidence=value)

    def test_invalid_runtime_rejected(self):
        for value in (-1, float("nan"), float("inf"), True, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.result, runtime=value)

    def test_request_requires_aware_timestamp(self):
        for value in (self.request.target_as_of_at.replace(tzinfo=None), "2026-09-24T12:00:00Z", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.request, target_as_of_at=value)
        self.assertEqual(self.request.target_as_of_at.utcoffset().total_seconds(), 0)

    def test_request_requires_capability_and_fingerprint(self):
        with self.assertRaises(ValueError):
            replace(self.request, operation="predict")
        for value in ("", " ", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.request, input_fingerprint=value)

    def test_seed_requires_integer_or_none(self):
        for value in (True, 1.5, "42"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.request, seed=value)
        self.assertIsNone(replace(self.request, seed=None).seed)

    def test_request_snapshots_and_deep_freezes_mutable_inputs(self):
        inputs = {"observations": [{"score": 1}], "parameters": {"weight": 0.5}}
        request = replace(self.request, inputs=inputs)
        inputs["observations"][0]["score"] = 999
        inputs["observations"].append({"score": 2})
        inputs["parameters"]["weight"] = 0
        self.assertEqual(request.inputs["observations"], ({"score": 1},))
        self.assertEqual(request.inputs["parameters"]["weight"], 0.5)
        with self.assertRaises(TypeError):
            request.inputs["observations"][0]["score"] = 3
        with self.assertRaises(TypeError):
            request.inputs["new"] = 4
        with self.assertRaises(FrozenInstanceError):
            request.input_fingerprint = "mutated"

    def test_result_snapshots_inputs_output_distribution_and_metadata(self):
        inputs = {"samples": [1]}
        output = {"probabilities": [0.4, 0.6]}
        distribution = {"support": [0, 1]}
        warnings = ["synthetic only"]
        result = replace(self.result, inputs=inputs, result=output,
                         distribution=distribution, warnings=warnings)
        inputs["samples"].append(2)
        output["probabilities"][0] = 0.99
        distribution["support"].append(2)
        warnings.append("late change")
        self.assertEqual(result.inputs["samples"], (1,))
        self.assertEqual(result.result["probabilities"], (0.4, 0.6))
        self.assertEqual(result.distribution["support"], (0, 1))
        self.assertEqual(result.warnings, ("synthetic only",))
        with self.assertRaises(TypeError):
            result.distribution["support"] = (2,)

    def test_nested_nonfinite_payloads_rejected_in_every_field(self):
        for number in (float("nan"), float("inf"), -float("inf")):
            payload = {"nested": [0, {"bad": number}]}
            with self.subTest(number=number, field="request"), self.assertRaises(ValueError):
                replace(self.request, inputs=payload)
            for field in ("inputs", "result", "distribution"):
                with self.subTest(number=number, field=field), self.assertRaises(ValueError):
                    replace(self.result, **{field: payload})

    def test_non_json_objects_and_keys_rejected(self):
        for payload in ({"value": object()}, {1: "bad-key"}, {"bad": {1, 2}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                replace(self.request, inputs=payload)
        for field in ("inputs", "distribution"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.result, **{field: [1, 2]})

    def test_cycles_rejected_but_shared_acyclic_values_are_copied(self):
        cycle = {}
        cycle["self"] = cycle
        with self.assertRaises(ValueError):
            replace(self.request, inputs=cycle)
        sequence = []
        sequence.append(sequence)
        with self.assertRaises(ValueError):
            replace(self.result, result=sequence)
        shared = [1, 2]
        request = replace(self.request, inputs={"a": shared, "b": shared})
        shared.append(3)
        self.assertEqual(request.inputs["a"], (1, 2))
        self.assertEqual(request.inputs["b"], (1, 2))

    def test_result_identity_hardware_and_metadata_require_text(self):
        for field in ("engine_id", "engine_version", "numerical_precision", "hardware"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.result, **{field: " "})
        for field in ("warnings", "assumptions", "reason_codes"):
            for value in ("not a sequence", (" ",), (None,)):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    replace(self.result, **{field: value})


if __name__ == "__main__":
    unittest.main()
