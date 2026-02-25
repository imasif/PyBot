# Calculation Skill

**Purpose:** Handle computation requests that clearly ask for math or unit conversions, such as "calculate 25 + 37" or "convert 100 Fahrenheit to Celsius".

**Triggers:** User text contains verbs like calculate, convert, compute, plus signs, or units. Avoid triggering when the intent is identity, small talk, or other service-specific commands.

**Behavior:** Send the prompt to the AI with explicit instructions to return only the numeric result in the "Result: ..." format. Wrap the final response with a math emoji and a short confirmation.

**Keywords:** calculation, conversion, math, numbers, units.
