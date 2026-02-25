import re


class CalculationService:
    def detect_request(self, text):
        text_lower = text.lower().strip()

        exclude_patterns = [
            r'what is (?:my|your|the) (?:id|user|name|telegram|chat)',
            r'what is (?:this|that|it)',
            r"what(?:\'s| is) (?:my|your)",
            r'who (?:am i|are you|is)',
            r'what (?:can you|are you)',
        ]

        for pattern in exclude_patterns:
            if re.search(pattern, text_lower):
                return None

        calc_patterns = [
            r'(?:calculate|compute) (.+?)(?:\?|$)',
            r'what is (\d+[\+\-\*/\^%].+?)(?:\?|$)',
            r'(\d+(?:\.\d+)?) (?:\+|\-|\*|\/|plus|minus|times|divided by) (.+)',
            r'convert (.+?) (?:to|into) (.+)',
            r'how many (.+?) (?:in|are in) (.+?)(?:\?|$)',
        ]

        for pattern in calc_patterns:
            if re.search(pattern, text_lower):
                return {'action': 'calculate', 'expression': text}

        return None

    def handle(self, expression, ask_ollama):
        prompt = f'''Calculate or convert this expression and provide only the result:
"{expression}"

If it's a math calculation, compute it.
If it's a unit conversion, convert it accurately.

Respond with ONLY the answer in this format:
Result: [answer with units if applicable]

Examples:
- "25 + 37" → Result: 62
- "convert 100 fahrenheit to celsius" → Result: 37.78°C
- "how many meters in 5 kilometers" → Result: 5000 meters
'''

        ai_response = ask_ollama(prompt, [])
        result_match = re.search(r'Result:\s*(.+?)(?:\n|$)', ai_response, re.IGNORECASE)
        if result_match:
            result = result_match.group(1).strip()
            return f"🔢 {result}"

        return f"🔢 {ai_response.strip()}"
