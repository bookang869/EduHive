# Use AWS Lambda Python base image
# Using 3.12 for compatibility
FROM public.ecr.aws/lambda/python:3.12

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Copy requirements first for better Docker layer caching
COPY requirements.txt ${LAMBDA_TASK_ROOT}/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
  pip install --no-cache-dir -r requirements.txt

# Copy application code (excluding files in .dockerignore)
COPY . ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler
# The handler is defined in api/main.py as 'handler' (Mangum wraps FastAPI)
CMD [ "api.main.handler" ]

