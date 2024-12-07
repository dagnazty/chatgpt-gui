# chatgpt_handler.py

import os
import json
import logging
import openai
import tiktoken
import time
import signal
from datetime import datetime
from dotenv import load_dotenv
from uuid import uuid4
from threading import Event
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from rate_limiter import RateLimiter  # Import the RateLimiter class

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    filename='chatgpt_handler.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s:%(message)s'
)

# Event for graceful shutdown
shutdown_event = Event()

def handle_exit_signal(signum, frame):
    logging.info(f"Received exit signal: {signum}")
    shutdown_event.set()

# Register signals for graceful shutdown
signal.signal(signal.SIGINT, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)

class ChatGPTHandler:
    """
    A handler class for interacting with OpenAI's o1-preview model,
    managing sessions, token limits, and message exchanges.
    """

    encoding = None  # Class-level variable to ensure single initialization

    def __init__(
        self,
        model: str = "o1-preview",
        max_context_tokens: int = 128000,
        max_response_tokens: int = 32768,
        system_prompt: str = None,
        session_name: str = None,
        session_dir: str = "sessions",
        rate_limit_max_calls: int = 60,  # Adjust based on your OpenAI plan
        rate_limit_period: float = 60.0,  # 60 seconds
    ):
        """
        Initializes the ChatGPTHandler.

        Args:
            model (str): The model to use for the API (default is "o1-preview").
            max_context_tokens (int): Maximum tokens allowed in the context.
            max_response_tokens (int): Maximum tokens allowed in the response.
            system_prompt (str): Optional system prompt to guide the assistant's behavior.
            session_name (str): Optional name for the session.
            session_dir (str): Directory to save session files.
            rate_limit_max_calls (int): Maximum number of API calls allowed within the period.
            rate_limit_period (float): Time period for rate limiting in seconds.
        """
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logging.critical("OPENAI_API_KEY is not set in the environment variables.")
            raise ValueError("OPENAI_API_KEY is not set in the environment variables.")
        openai.api_key = self.api_key
        logging.info("Initialized ChatGPTHandler.")

        # Session management
        self.session_dir = session_dir
        os.makedirs(self.session_dir, exist_ok=True)
        self.session_name = session_name or f"session_{uuid4()}"
        self.session_file = os.path.join(self.session_dir, f"{self.session_name}.json")
        self.session = {"messages": []}
        self.session_changed = False

        # Load existing session if available
        if os.path.exists(self.session_file):
            self.load_session()
        else:
            if system_prompt:
                self.session["messages"].append({"role": "system", "content": system_prompt})
            self.session_changed = True
            self.save_session()

        self.model = model

        # Initialize tiktoken encoding
        if not ChatGPTHandler.encoding:
            ChatGPTHandler.encoding = tiktoken.encoding_for_model(self.model)
        self.encoding = ChatGPTHandler.encoding

        # Set token limits based on the model specifications
        self.max_context_tokens = max_context_tokens
        self.max_response_tokens = max_response_tokens

        # Initialize RateLimiter
        self.rate_limiter = RateLimiter(rate_limit_max_calls, rate_limit_period)

    def start_new_session(self, session_name: str = None, system_prompt: str = None):
        """
        Starts a new session with an optional session name and system prompt.

        Args:
            session_name (str): Optional name for the session.
            system_prompt (str): Optional system prompt to guide the assistant's behavior.
        """
        self.session_name = session_name or f"session_{uuid4()}"
        self.session_file = os.path.join(self.session_dir, f"{self.session_name}.json")
        self.session = {"messages": []}
        if system_prompt:
            self.session["messages"].append({"role": "system", "content": system_prompt})
        self.session_changed = True
        logging.info(f"Started new session: {self.session_name}")
        self.save_session()

    def count_tokens(self, messages: list) -> int:
        """
        Returns the total number of tokens used by a list of messages.

        Args:
            messages (list): List of messages in the session.

        Returns:
            int: Total token count for the messages.
        """
        try:
            # Adjust token counting based on model specifications
            tokens_per_message = 4  # Based on gpt-3.5-turbo's tokenization
            tokens_per_name = -1    # If a 'name' is present, adjust accordingly
            num_tokens = 0
            for message in messages:
                num_tokens += tokens_per_message
                for key, value in message.items():
                    num_tokens += len(self.encoding.encode(value))
                    if key == "name":
                        num_tokens += tokens_per_name
            num_tokens += 2  # Every reply is primed with the assistant's tokens
            return num_tokens
        except Exception as e:
            logging.error(f"Error in count_tokens: {e}")
            return 0

    def manage_token_limit(self):
        """
        Ensures the conversation stays within token limits.
        """
        while True:
            total_tokens = self.count_tokens(self.session["messages"]) + self.max_response_tokens
            if total_tokens <= self.max_context_tokens:
                break
            # Remove the oldest message (after system prompt if present)
            if len(self.session["messages"]) > 1:
                removed_message = self.session["messages"].pop(1)
                self.session_changed = True
                logging.info(f"Removed message to stay within token limit: {removed_message}")
            else:
                # Can't remove further without losing the current message
                logging.warning("Cannot remove more messages; reached token limit.")
                break

    def save_session(self):
        """
        Saves the session data to a JSON file with the session name.
        """
        if not self.session_changed:
            return
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.session, f, indent=2)
            self.session_changed = False
            logging.info(f"Session saved to {self.session_file}")
        except Exception as e:
            logging.error(f"Failed to save session: {e}")

    def load_session(self, session_data: dict = None):
        """
        Loads session data from the session file or provided data.

        Args:
            session_data (dict, optional): The session data to load. If None, loads from the file.
        """
        try:
            if session_data:
                self.session = session_data
            else:
                with open(self.session_file, 'r') as f:
                    self.session = json.load(f)
            self.session_changed = False
            logging.info(f"Loaded session from {self.session_file}")
        except Exception as e:
            logging.error(f"Failed to load session: {e}")
            self.session = {"messages": []}

    def get_session_data(self) -> dict:
        """
        Returns the current session data.

        Returns:
            dict: The session data.
        """
        return self.session

    @retry(
        retry=retry_if_exception_type(
            (openai.error.APIError,
             openai.error.Timeout,
             openai.error.TryAgain,
             openai.error.ServiceUnavailableError,
             openai.error.RateLimitError)
        ),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def call_openai_api(self):
        """
        Makes a call to the OpenAI API with exponential backoff.

        Returns:
            dict: The API response.
        """
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=self.session["messages"],
            max_completion_tokens=self.max_response_tokens,
        )
        return response

    def send_message(self, user_input: str) -> str:
        """
        Sends a message to the ChatGPT API and returns the assistant's response.

        Args:
            user_input (str): The user's message.

        Returns:
            str: The assistant's response.
        """
        if not user_input.strip():
            logging.warning("Empty user input received.")
            return "⚠️ Please provide a valid input."

        # Acquire a token before making the API call
        self.rate_limiter.acquire()

        # Append user message to the session
        self.session["messages"].append({"role": "user", "content": user_input})
        self.session_changed = True
        logging.info("User input added to session.")

        # Manage the token limits
        self.manage_token_limit()

        try:
            response = self.call_openai_api()

            if response and 'choices' in response and len(response['choices']) > 0:
                answer = response['choices'][0]['message']['content'].strip()
                logging.info("Received response from OpenAI API.")

                # Append assistant's response to the session
                self.session["messages"].append({"role": "assistant", "content": answer})
                self.session_changed = True

                # Save the session
                self.save_session()

                return answer
            else:
                logging.warning("No response received from the OpenAI API.")
                return "⚠️ No response received from the assistant."

        except openai.error.AuthenticationError as e:
            logging.error(f"Authentication error: {e}")
            return "❌ Authentication error: Check your API key."
        except openai.error.RateLimitError as e:
            logging.error(f"Rate limit exceeded: {e}")
            return "⚠️ Rate limit exceeded. Please try again later."
        except openai.error.OpenAIError as e:
            logging.error(f"OpenAI API error: {e}")
            return f"❌ OpenAI API error: {e}"
        except Exception as e:
            logging.exception("An unexpected error occurred.")
            return f"❌ An unexpected error occurred: {e}"

    def run(self):
        """
        Runs the handler, ensuring that the session is saved upon shutdown.
        """
        try:
            while not shutdown_event.is_set():
                # Your main loop code here
                time.sleep(1)
        finally:
            self.save_session()
            logging.info("Session saved before shutdown.")

# Usage example
if __name__ == "__main__":
    handler = ChatGPTHandler()
    try:
        response = handler.send_message("Hello, how are you?")
        print(response)
    except Exception as e:
        logging.exception("An error occurred in the main execution.")
    finally:
        handler.save_session()
