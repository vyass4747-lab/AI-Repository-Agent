from langchain_groq import ChatGroq

from ai_repository_agent.config import GROQ_API_KEY
from langchain_core.messages import SystemMessage, HumanMessage
from ai_repository_agent.tools.filesyatem import list_repository_tool, read_file

# def main():

#     print("starting application.....")

#     llm = ChatGroq(
#         model = "openai/gpt-oss-20b",
#         api_key=GROQ_API_KEY,
#         temperature=0

#     )

#     # response = llm.invoke("explain what does an AI repository agent does ?? ")


# #     response = llm.invoke(
# #     """
# #     You are an AI-powered Repository Engineering Agent.

# #     Your purpose is to help developers understand and debug
# #     software code repositories.

# #     You should be able to:
# #     1. Explore project files and understand code structure.
# #     2. Investigate bugs and runtime errors.
# #     3. Identify potential root causes.
# #     4. Propose code fixes.
# #     5. Run tests and verify proposed solutions.

# #     Explain your role in this project in simple words.
# #     """
# # )


#     messages = [
#         SystemMessage(
#             content="You are an AI Repository Engineering Agent. "
#                     "Help developers understand and debug software repositories."
#         ),
#         HumanMessage(
#             content="What will your responsibilities be in this project?"
#         )
#     ]

#     response = llm.invoke(messages)

#     print(response.content)
#     print(response.response_metadata)
#     print(type(response))


#     print("end application....")


# # if __name__ == "__main__":
# #     main()


def main():

    print("\n--- Repository Files ---")
    result = list_repository_tool.invoke({})
    print(result)

    print("\n--- Reading main.py ---")
    content = read_file.invoke({
        "file_path": "src/ai_repository_agent/main.py"
    })
    print(content)


if __name__ == "__main__":
    main()


