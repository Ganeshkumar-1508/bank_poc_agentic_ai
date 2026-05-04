#!/usr/bin/env python3
"""
FannieMaeInference - LLM-friendly loader for all five trained models.

This module provides a simple interface for loading and using the trained
MLJAR models for inference. It is designed to be easily integrated with
LLM applications.

Inference Output Metrics by Task Type:
- binary_classification: prediction, probability, confidence
- multiclass_classification: prediction, probabilities, confidence, top_k_classes
- regression: prediction, residual (if actual provided), confidence_interval
- clustering: cluster_label, cluster_distance, cluster_confidence

Usage:
    from inference_helper import FannieMaeInference

    # Load a specific model
    infer = FannieMaeInference("fannie_mae_models/credit_risk")
    print(infer.info)

    # Make predictions
    preds = infer.predict(X_df)

    # Get probabilities (classification only)
    probas = infer.predict_proba(X_df)

    # Get predictions with metrics
    results = infer.predict_with_metrics(X_df)

    # Load all models
    from inference_helper import FannieMaeModelHub
    hub = FannieMaeModelHub("fannie_mae_models")
    credit_risk = hub.get_model("credit_risk")
    predictions = credit_risk.predict(sample_data)
"""

import json
import pickle
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class FannieMaeInference:
    """
    LLM-friendly inference wrapper for a single Fannie Mae model.

    Attributes:
        info: Dictionary with model metadata (use_case, task_type, target, etc.)
        feature_names: List of feature names required for prediction
        use_case: Name of the use case (credit_risk, customer_segmentation, etc.)
        task_type: Type of task (binary_classification, regression, clustering, etc.)
    """

    def __init__(self, model_dir: str):
        """
        Initialize the inference wrapper.

        Args:
            model_dir: Path to the model directory (e.g., "fannie_mae_models/credit_risk")
        """
        self.model_dir = Path(model_dir)

        if not self.model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        # Load metadata
        meta_path = next(self.model_dir.glob("*_metadata.json"), None)
        if not meta_path:
            raise FileNotFoundError(f"No metadata file found in {model_dir}")

        with open(meta_path) as f:
            self.meta = json.load(f)

        # Load model artifacts
        pkl_path = next(self.model_dir.glob("*_best_model.pkl"), None)
        if not pkl_path:
            raise FileNotFoundError(f"No model pickle found in {model_dir}")

        with open(pkl_path, "rb") as f:
            self.arts = pickle.load(f)

        # Extract key information
        self.task_type = self.meta["model"]["task_type"]
        self.feature_names = self.meta["features"]["feature_names"]
        self.use_case = self.meta["use_case"]
        self.target_column = self.meta["model"]["target_column"]
        self.label_map = self.meta["model"].get("label_map")

        log.info(
            f"[FannieMaeInference] {self.use_case} | task={self.task_type} | "
            f"{len(self.feature_names)} features"
        )

    @property
    def info(self) -> Dict[str, Any]:
        """
        Get model information dictionary.

        Returns:
            Dictionary with model metadata
        """
        return {
            "use_case": self.use_case,
            "task_type": self.task_type,
            "target": self.target_column,
            "n_features": len(self.feature_names),
            "feature_names": self.feature_names,
            "label_map": self.label_map,
            "train_years": self.meta["dataset"].get("train_years"),
            "test_year": self.meta["dataset"].get("test_year"),
            "metrics": self.meta["performance_metrics"],
            "description": self.meta.get("description", ""),
        }

    def _preprocess_supervised(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess data for supervised models: encode categoricals, fill NaN.

        Models trained via GPUTrainer receive data where categorical columns have
        already been encoded to integer codes (astype('category').cat.codes).
        We must replicate that same encoding at inference time so that all
        feature columns are numeric (int/float/bool) before the model sees them.

        Args:
            X: Aligned DataFrame with features

        Returns:
            DataFrame with all columns converted to numeric dtypes
        """
        X_encoded = X.copy()

        for col in X_encoded.columns:
            dtype = X_encoded[col].dtype
            # Check for object, category, or pandas StringDtype (newer pandas versions)
            is_string_dtype = (
                dtype == "object"
                or dtype.name == "category"
                or str(dtype).startswith("string")
                or pd.api.types.is_string_dtype(dtype)
            )

            if is_string_dtype:
                # Match GPUTrainer._encode_categoricals():
                # df[col] = df[col].astype('category').cat.codes.astype(np.int32)
                # cat.codes maps NaN → -1, which is the convention the model learned
                X_encoded[col] = (
                    X_encoded[col].astype("category").cat.codes.astype(np.int32)
                )
            elif dtype == "bool":
                X_encoded[col] = X_encoded[col].astype(np.int32)

        # Fill remaining NaN in numeric columns with 0 (CatBoost / LightGBM handle
        # NaN natively, but some pipelines like XGBoost may not)
        for col in X_encoded.columns:
            if X_encoded[col].isna().any():
                X_encoded[col] = X_encoded[col].fillna(0)

        return X_encoded

    def _preprocess_clustering(self, X: pd.DataFrame) -> np.ndarray:
        """
        Preprocess data for clustering: encode categoricals, fill NaN, scale.

        This must match the preprocessing applied during training in
        MLJARTrainer._train_clustering() / GPUTrainer._train_clustering_cpu().

        Args:
            X: Aligned DataFrame with features

        Returns:
            Scaled numpy array ready for KMeans prediction
        """
        from sklearn.preprocessing import LabelEncoder

        X_encoded = X.copy()
        label_encoders = self.arts.get("label_encoders", {})

        for col in X_encoded.columns:
            if col in label_encoders:
                # Use the same LabelEncoder from training
                le = label_encoders[col]
                # Handle unseen categories by converting to string and using known classes
                X_encoded[col] = X_encoded[col].fillna("MISSING").astype(str)
                # Transform, mapping unseen labels to a default (0)
                X_encoded[col] = X_encoded[col].apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else 0
                )
            elif (
                X_encoded[col].dtype == "object"
                or X_encoded[col].dtype.name == "category"
            ):
                # No saved encoder — encode on the fly (fallback)
                X_encoded[col] = X_encoded[col].fillna("MISSING").astype(str)
                le = LabelEncoder()
                X_encoded[col] = le.fit_transform(X_encoded[col])
            else:
                # Numeric column (covers all numeric dtypes, not just a hardcoded list)
                if X_encoded[col].isna().any():
                    non_nan = X_encoded[col].dropna()
                    if len(non_nan) == 0:
                        # All-NaN column (e.g. added by _align() for missing features)
                        median_val = 0
                    else:
                        median_val = non_nan.median()
                    X_encoded[col] = X_encoded[col].fillna(median_val)

        # Scale using the saved scaler from training
        scaler = self.arts.get("scaler")
        if scaler is not None:
            return scaler.transform(X_encoded)
        else:
            log.warning(
                "No scaler found in model artifacts. Using unscaled data (predictions may be incorrect)."
            )
            return X_encoded.values

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Make predictions.

        Args:
            X: DataFrame with features (columns should match feature_names)

        Returns:
            Array of predictions
        """
        X = self._align(X)

        if "clustering" in self.task_type:
            kmeans = self.arts.get("clustering")
            if kmeans is None:
                raise ValueError("No clustering model loaded")

            X_scaled = self._preprocess_clustering(X)
            return kmeans.predict(X_scaled)

        if self.arts.get("automl") is None:
            raise ValueError("No model loaded")

        X = self._preprocess_supervised(X)
        return self.arts["automl"].predict(X)

    def predict_with_metrics(
        self, X: pd.DataFrame, actual: Optional[pd.Series] = None
    ) -> Dict[str, Any]:
        """
        Make predictions with task-specific output metrics.

        This method returns predictions along with additional metrics based on
        the task type, as defined in the metrics configuration.

        Args:
            X: DataFrame with features
            actual: Optional actual values for computing residuals/errors

        Returns:
            Dictionary with predictions and task-specific metrics:

            For binary_classification:
                {
                    "predictions": [0, 1, 0, ...],
                    "probabilities": [0.1, 0.9, 0.2, ...],
                    "confidence": [0.9, 0.9, 0.8, ...],
                }

            For multiclass_classification:
                {
                    "predictions": [0, 2, 1, ...],
                    "probabilities": [[0.8, 0.1, 0.1], [0.1, 0.2, 0.7], ...],
                    "confidence": [0.8, 0.7, 0.7, ...],
                    "top_k_classes": [[(0, 0.8), (1, 0.1), ...], ...],
                }

            For regression:
                {
                    "predictions": [100.5, 200.3, ...],
                    "confidence_interval": [[95, 105], [195, 205], ...],  # if available
                }

            For clustering:
                {
                    "cluster_labels": [0, 2, 1, ...],
                    "cluster_distance": [1.5, 2.3, 1.1, ...],
                    "cluster_confidence": [0.85, 0.72, 0.91, ...],
                }
        """
        X_aligned = self._align(X)
        result = {"task_type": self.task_type}

        if "clustering" in self.task_type:
            # Clustering predictions — use proper preprocessing (encode + scale)
            kmeans = self.arts.get("clustering")
            if kmeans is None:
                raise ValueError("No clustering model loaded")

            X_scaled = self._preprocess_clustering(X_aligned)

            labels = kmeans.predict(X_scaled)
            distances = kmeans.transform(X_scaled).min(axis=1)

            # Confidence based on distance (inverse)
            confidence = 1 / (1 + distances)

            result["cluster_labels"] = labels.tolist()
            result["cluster_distance"] = distances.tolist()
            result["cluster_confidence"] = confidence.tolist()

        elif "classification" in self.task_type:
            # Classification predictions
            if self.arts.get("automl") is None:
                raise ValueError("No model loaded")

            X_prep = self._preprocess_supervised(X_aligned)
            predictions = self.arts["automl"].predict(X_prep)
            probabilities = self.arts["automl"].predict_proba(X_prep)

            if len(probabilities.shape) == 1:
                # Binary classification
                result["predictions"] = predictions.tolist()
                result["probabilities"] = probabilities.tolist()
                result["confidence"] = np.maximum(
                    probabilities, 1 - probabilities
                ).tolist()
            else:
                # Multiclass classification
                result["predictions"] = predictions.tolist()
                result["probabilities"] = probabilities.tolist()
                result["confidence"] = probabilities.max(axis=1).tolist()

                # Top K classes with probabilities
                k = min(3, probabilities.shape[1])
                top_k_indices = np.argsort(probabilities, axis=1)[:, -k:][:, ::-1]
                top_k_probs = np.take_along_axis(probabilities, top_k_indices, axis=1)

                result["top_k_classes"] = []
                for i in range(len(predictions)):
                    classes = []
                    for j in range(k):
                        classes.append(
                            {
                                "class": int(top_k_indices[i, j]),
                                "probability": float(top_k_probs[i, j]),
                            }
                        )
                    result["top_k_classes"].append(classes)

        elif self.task_type == "regression":
            # Regression predictions
            if self.arts.get("automl") is None:
                raise ValueError("No model loaded")

            X_prep = self._preprocess_supervised(X_aligned)
            predictions = self.arts["automl"].predict(X_prep)
            result["predictions"] = predictions.tolist()

            # Compute residuals if actual values provided
            if actual is not None:
                residuals = actual.values - predictions
                result["residuals"] = residuals.tolist()

            # Note: Confidence intervals would require additional model-specific logic
            # For now, we leave this as a placeholder
            result["confidence_interval"] = None

        return result

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Get prediction probabilities (classification only).

        Args:
            X: DataFrame with features

        Returns:
            Array of probabilities
        """
        if "clustering" in self.task_type:
            log.warning("Clustering does not support predict_proba")
            return self.predict(X)

        X_aligned = self._align(X)
        X_prep = self._preprocess_supervised(X_aligned)
        return self.arts["automl"].predict_proba(X_prep)

    def predict_with_explanation(
        self, X: pd.DataFrame, top_n_features: int = 5
    ) -> Dict[str, Any]:
        """
        Make predictions with feature importance explanation.

        Args:
            X: DataFrame with features
            top_n_features: Number of top features to include in explanation

        Returns:
            Dictionary with predictions and explanations
        """
        X_aligned = self._align(X)
        predictions = self.predict(X)

        # Get feature importance if available
        feature_importance = None
        if self.arts.get("automl") is not None:
            try:
                importance = self.arts["automl"].feature_importance
                if isinstance(importance, dict) and "importance" in importance:
                    df = pd.DataFrame(importance["importance"])
                    df.columns = ["feature", "importance"]
                    feature_importance = (
                        df.sort_values("importance", ascending=False)
                        .head(top_n_features)
                        .to_dict("records")
                    )
            except Exception as e:
                log.warning(f"Could not get feature importance: {e}")

        return {
            "predictions": predictions.tolist(),
            "feature_importance": feature_importance,
            "input_features": X_aligned.columns.tolist(),
        }

    def get_inference_output_schema(self) -> Dict[str, Any]:
        """
        Get the expected output schema for this model's inference.

        Returns:
            Dictionary describing the output fields and their types
        """
        schemas = {
            "binary_classification": {
                "predictions": {
                    "type": "array",
                    "items": "int",
                    "description": "Binary predictions (0 or 1)",
                },
                "probabilities": {
                    "type": "array",
                    "items": "float",
                    "description": "Probability of positive class",
                },
                "confidence": {
                    "type": "array",
                    "items": "float",
                    "description": "Confidence score (max probability)",
                },
            },
            "multiclass_classification": {
                "predictions": {
                    "type": "array",
                    "items": "int",
                    "description": "Predicted class labels",
                },
                "probabilities": {
                    "type": "array",
                    "items": "array",
                    "description": "All class probabilities",
                },
                "confidence": {
                    "type": "array",
                    "items": "float",
                    "description": "Confidence score (max probability)",
                },
                "top_k_classes": {
                    "type": "array",
                    "items": "array",
                    "description": "Top K classes with probabilities",
                },
            },
            "regression": {
                "predictions": {
                    "type": "array",
                    "items": "float",
                    "description": "Predicted continuous values",
                },
                "residuals": {
                    "type": "array",
                    "items": "float",
                    "description": "Prediction errors (if actual provided)",
                },
                "confidence_interval": {
                    "type": "array",
                    "items": "array",
                    "description": "Prediction intervals (if available)",
                },
            },
            "clustering": {
                "cluster_labels": {
                    "type": "array",
                    "items": "int",
                    "description": "Assigned cluster IDs",
                },
                "cluster_distance": {
                    "type": "array",
                    "items": "float",
                    "description": "Distance to cluster centroid",
                },
                "cluster_confidence": {
                    "type": "array",
                    "items": "float",
                    "description": "Confidence in cluster assignment",
                },
            },
        }

        return {
            "use_case": self.use_case,
            "task_type": self.task_type,
            "output_schema": schemas.get(self.task_type, {}),
            "feature_requirements": self.get_feature_requirements(),
        }

    def _align(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Align input DataFrame to training feature schema.

        Args:
            X: Input DataFrame

        Returns:
            DataFrame with aligned features
        """
        X = X.copy()

        # Add missing features with NaN
        for col in self.feature_names:
            if col not in X.columns:
                X[col] = np.nan

        # Return only the features in the correct order
        return X[self.feature_names]

    def get_feature_requirements(self) -> Dict[str, Any]:
        """
        Get information about required features.

        Returns:
            Dictionary with feature requirements
        """
        return {
            "n_features": len(self.feature_names),
            "feature_names": self.feature_names,
            "categorical_features": self.meta["features"].get(
                "categorical_features", []
            ),
            "numerical_features": self.meta["features"].get("numerical_features", []),
        }


class FannieMaeModelHub:
    """
    Hub for managing multiple Fannie Mae models.

    Usage:
        hub = FannieMaeModelHub("fannie_mae_models")
        credit_risk = hub.get_model("credit_risk")
        segmentation = hub.get_model("customer_segmentation")

        # Get all model info
        for name, info in hub.get_all_info().items():
            print(f"{name}: {info['task_type']}")
    """

    def __init__(self, base_dir: str):
        """
        Initialize the model hub.

        Args:
            base_dir: Base directory containing model subdirectories
        """
        self.base_dir = Path(base_dir)
        self._models: Dict[str, FannieMaeInference] = {}

        # Discover available models
        self.available_models = self._discover_models()

    def _discover_models(self) -> List[str]:
        """Discover available model directories."""
        models = []
        for item in self.base_dir.iterdir():
            if item.is_dir() and (item / f"{item.name}_metadata.json").exists():
                models.append(item.name)
        return sorted(models)

    def get_model(self, use_case: str) -> FannieMaeInference:
        """
        Get a model by use case name.

        Args:
            use_case: Use case name (credit_risk, customer_segmentation, etc.)

        Returns:
            FannieMaeInference instance
        """
        if use_case not in self.available_models:
            raise ValueError(
                f"Unknown use case: {use_case}. " f"Available: {self.available_models}"
            )

        if use_case not in self._models:
            model_dir = self.base_dir / use_case
            self._models[use_case] = FannieMaeInference(str(model_dir))

        return self._models[use_case]

    def get_all_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all available models.

        Returns:
            Dictionary mapping use case names to model info
        """
        return {name: self.get_model(name).info for name in self.available_models}

    def predict_all(
        self, X: pd.DataFrame, use_cases: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Make predictions with all models.

        Args:
            X: DataFrame with features
            use_cases: List of use cases to run (None = all)

        Returns:
            Dictionary mapping use case names to predictions
        """
        if use_cases is None:
            use_cases = self.available_models

        results = {}
        for use_case in use_cases:
            try:
                model = self.get_model(use_case)
                # Use predict_with_metrics for richer output
                metrics_result = model.predict_with_metrics(X)
                results[use_case] = {
                    **metrics_result,
                    "task_type": model.task_type,
                }
            except Exception as e:
                results[use_case] = {"error": str(e)}

        return results

    def predict_all_with_schema(
        self, X: pd.DataFrame, use_cases: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Make predictions with all models and include output schemas.

        Args:
            X: DataFrame with features
            use_cases: List of use cases to run (None = all)

        Returns:
            Dictionary with predictions and schemas for each model
        """
        if use_cases is None:
            use_cases = self.available_models

        results = {"predictions": {}, "schemas": {}}

        for use_case in use_cases:
            try:
                model = self.get_model(use_case)
                results["predictions"][use_case] = model.predict_with_metrics(X)
                results["schemas"][use_case] = model.get_inference_output_schema()
            except Exception as e:
                results["predictions"][use_case] = {"error": str(e)}
                results["schemas"][use_case] = {"error": str(e)}

        return results


def load_model(model_dir: str) -> FannieMaeInference:
    """
    Convenience function to load a model.

    Args:
        model_dir: Path to model directory

    Returns:
        FannieMaeInference instance
    """
    return FannieMaeInference(model_dir)


def load_all_models(base_dir: str = "fannie_mae_models") -> FannieMaeModelHub:
    """
    Convenience function to load all models.

    Args:
        base_dir: Base directory containing models

    Returns:
        FannieMaeModelHub instance
    """
    return FannieMaeModelHub(base_dir)


# Example usage for LLM integration
if __name__ == "__main__":
    # Load all models
    hub = FannieMaeModelHub("fannie_mae_models")

    print("Available models:")
    for name, info in hub.get_all_info().items():
        print(f" - {name}: {info['task_type']} ({info['n_features']} features)")

    # Example: Show inference output schema for each model
    print("\nInference Output Schemas:")
    for name in hub.available_models:
        model = hub.get_model(name)
        schema = model.get_inference_output_schema()
        print(f"\n{name} ({schema['task_type']}):")
        for field, details in schema["output_schema"].items():
            print(f"  - {field}: {details['description']}")

    # Example: Load sample data and make predictions with metrics
    # sample_data = pd.DataFrame({...})
    # results = hub.predict_all_with_schema(sample_data)
    # print(json.dumps(results, indent=2))
