import logging
from typing import Dict, List, Optional

import config


logger = logging.getLogger(__name__)


class UniversalNLUService:
    def __init__(self):
        self.enabled = bool(getattr(config, 'NLU_ENABLED', True))
        self.model_name = getattr(config, 'NLU_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
        self.min_confidence = float(getattr(config, 'NLU_MIN_CONFIDENCE', 0.22))

        self._model = None
        self._util = None
        self._intent_vectors: Dict[str, object] = {}

        self._intent_examples: Dict[str, List[str]] = {
            'weather': [
                'what is the weather like',
                'will it rain today',
                'forecast please',
                'temperature now',
            ],
            'news': [
                'show me latest news',
                'what is happening today in the world',
                'headlines please',
            ],
            'search': [
                'search the web for this',
                'look this up online',
                'find information about this topic',
                'find web results for this',
                'google this for me',
            ],
            'wikipedia': [
                'tell me about this person',
                'who is this',
                'give me encyclopedia info',
            ],
            'status': [
                'show bot status',
                'are you running',
                'system health check',
            ],
            'briefing': [
                'give me daily briefing',
                'morning summary please',
                'brief me now',
            ],
            'notes': [
                'create a note for me',
                'save this as a note',
                'show my notes',
            ],
            'shopping': [
                'add item to shopping list',
                'show shopping list',
                'clear shopping list',
            ],
            'timer': [
                'set a timer',
                'start countdown',
                'show active timers',
            ],
        }

        self._initialize_model()

    def _initialize_model(self):
        if not self.enabled:
            logger.info('Universal NLU disabled by config (NLU_ENABLED=false).')
            return

        try:
            from sentence_transformers import SentenceTransformer, util
        except Exception as exc:
            logger.warning(f'Universal NLU unavailable (sentence-transformers not installed): {exc}')
            self.enabled = False
            return

        try:
            self._model = SentenceTransformer(self.model_name)
            self._util = util
            for intent, samples in self._intent_examples.items():
                self._intent_vectors[intent] = self._model.encode(
                    samples,
                    convert_to_tensor=True,
                    normalize_embeddings=True,
                )
            logger.info(f'Universal NLU initialized with model: {self.model_name}')
        except Exception as exc:
            logger.warning(f'Universal NLU model init failed: {exc}')
            self.enabled = False
            self._model = None
            self._util = None
            self._intent_vectors = {}

    def detect_intent(self, text: str) -> Optional[Dict[str, float]]:
        if not text or not self.enabled or self._model is None or self._util is None:
            return None

        try:
            query_vector = self._model.encode(text, convert_to_tensor=True, normalize_embeddings=True)
            best_intent = None
            best_score = -1.0

            for intent, vectors in self._intent_vectors.items():
                similarity_scores = self._util.cos_sim(query_vector, vectors)
                score = float(similarity_scores.max().item())
                if score > best_score:
                    best_score = score
                    best_intent = intent

            if best_intent is None or best_score < self.min_confidence:
                return None

            return {'intent': best_intent, 'confidence': best_score}
        except Exception as exc:
            logger.debug(f'Universal NLU detect_intent failed: {exc}')
            return None
