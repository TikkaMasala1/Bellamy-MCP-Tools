## Prerequisites

* Python 3.8+
* `CCSK.pdf` file (must be placed in the root directory of the project).
* A Google Gemini API Key.

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd <your-repository-name>
    ```

2.  **Create and Activate a Conda Environment (Recommended)**

    If you prefer using Conda for environment management:

    1.  **Create a new Conda environment:**
        Replace `myenv` with your preferred environment name and specify your desired Python version (e.g., ```python=3.9```), leaving it```python``` will download the latest verision
        ```bash
        conda create --name myenv python
        ```

    2.  **Activate the Conda environment:**
        ```bash
        conda activate myenv
        ```
        Your command prompt should now indicate that the Conda environment is active.

        ![Screenshot From 2025-05-22 19-17-54.png](imgs/Screenshot%20From%202025-05-22%2019-17-54.png)
        

    
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    
4.  **Set up environment variables:**
    Create a `.env` file in the root of your project and add your Google Gemini API Key:
    ```env
    GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
    ```    
    
##  Running the Application

To run the FastAPI server, use Uvicorn:

```bash
uvicorn mcp:app --reload --port 8000