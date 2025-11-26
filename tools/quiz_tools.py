from langchain_core.tools import tool
from typing import Literal, List
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field

class Question(BaseModel):
  question: str = Field(description="The quiz question")
  options: List[str] = Field(descriptions="Exactly 4 multiple choice options, labeled A, B, C, D")
  correct_answer: str = Field(description="The correct answer (MUST MATCH ONE OF 'options')")
  explanation: str = Field(description="Explanation of why the answer is correct and why the other ones are wrong")

class Quiz(BaseModel):
  topic: str = Field(description="The main topic being tested")
  questions: List[Question] = Field(description="List of the quiz questions")

@tool
def generate_quiz(
  research_text: str,
  topic: str, 
  difficulty: Literal["easy", "medium", "hard"], 
  num_questions: int
):
  """
  Generate a structured quiz with multiple choice questions based on research information.

    Args:
        research_text: str - Research information about the topic. This can be:
                      - Raw text from web searches
                      - Summary of research findings
                      - Any relevant information about the topic
                      - If empty, will generate questions from general knowledge

        topic: str - The main topic/subject for the quiz (e.g., "Python programming", "World War 2", "Photosynthesis")

        difficulty: Literal["easy", "medium", "hard"] - The difficulty level:
                   - "easy": Basic concepts, definitions, simple facts
                   - "medium": Application of concepts, connections between ideas
                   - "hard": Complex analysis, synthesis, advanced understanding

        num_questions: int - Number of questions to generate (between 1-30)
                      Common values: 3-5 (short), 6-10 (medium), 11-15 (long)

    Returns:
        Quiz object with structured questions, each having:
        - question: The question text
        - options: List of 4 multiple choice answers
        - correct_answer: The right answer (matching one option exactly)
        - explanation: Detailed explanation of the correct answer

    Example usage:
        research_info = "Machine learning is a subset of AI that focuses on algorithms..."
        quiz = generate_quiz(research_info, "Machine Learning", "medium", 5)
  """

  llm = init_chat_model("openai:gpt-4o")

  structured_llm = llm.with_structured_output(Quiz)

  prompt = f"""
  Create a {difficulty} quiz about {topic} with {num_questions} questions using the following research information.

  <RESEARCH_INFORMATION>
  {research_text}
  </RESEARCH_INFORMATION>

  Make sure to use the RESEARCH_INFORMATION to create the most accurate questions.
  """

  quiz = structured_llm.invoke(prompt)

  return quiz