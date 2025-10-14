import os
import csv
import uuid
import time
import jwt
import requests
from io import StringIO
from google.cloud import bigquery
from github import Github

def get_github_token():
    """Generates a GitHub App installation token."""
    private_key = os.environ.get("GITHUB_PRIVATE_KEY")
    app_id = os.environ.get("GITHUB_APP_ID")
    installation_id = os.environ.get("GITHUB_INSTALLATION_ID")

    # Generate the JWT
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + (10 * 60),
        "iss": app_id,
    }
    encoded_jwt = jwt.encode(payload, private_key, algorithm="RS256")

    # Get the installation access token
    headers = {
        "Authorization": f"Bearer {encoded_jwt}",
        "Accept": "application/vnd.github.v3+json",
    }
    response = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers=headers,
    )
    response.raise_for_status()
    return response.json()["token"]

def process_csv_files():
    """
    This function identifies modified CSV files in a commit, parses them,
    and merges the data into a BigQuery table.
    """
    # --- GitHub Integration ---
    github_token = get_github_token()
    g = Github(github_token)

    repo_name = os.environ.get("REPO_NAME")
    commit_sha = os.environ.get("COMMIT_SHA")
    repo = g.get_repo(repo_name)
    commit = repo.get_commit(sha=commit_sha)

    modified_csv_files = [f.filename for f in commit.files if f.filename.endswith(".csv")]

    if not modified_csv_files:
        print("No modified CSV files found in this commit.")
        return

    # --- BigQuery Integration ---
    project_id = os.environ.get("GCP_PROJECT")
    dataset_id = os.environ.get("BIGQUERY_DATASET", "your_dataset")
    table_id = os.environ.get("BIGQUERY_TABLE", "your_table")
    client = bigquery.Client(project=project_id)
    target_table_ref = client.dataset(dataset_id).table(table_id)

    try:
        target_table = client.get_table(target_table_ref)
    except Exception as e:
        print(f"Error getting target table: {e}")
        return

    # Process each modified CSV file
    for file_path in modified_csv_files:
        print(f"Processing file: {file_path}")
        content_string = repo.get_contents(file_path, ref=commit_sha).decoded_content.decode("utf-8")

        csv_file = StringIO(content_string)
        reader = csv.DictReader(csv_file)

        rows_to_insert = []
        for row in reader:
            try:
                row['id'] = int(row['id'])
                row['value'] = int(row['value'])
                rows_to_insert.append(row)
            except (ValueError, KeyError) as e:
                print(f"Skipping row due to parsing error: {row}. Error: {e}")

        if not rows_to_insert:
            print(f"No valid rows to process from {file_path}.")
            continue

        # Create a temporary staging table
        staging_table_id = f"staging_{uuid.uuid4().hex}"
        staging_table_ref = client.dataset(dataset_id).table(staging_table_id)
        staging_table = bigquery.Table(staging_table_ref, schema=target_table.schema)

        try:
            staging_table = client.create_table(staging_table)
            print(f"Created staging table {staging_table_id}")

            errors = client.insert_rows_json(staging_table_ref, rows_to_insert)
            if errors:
                print(f"Errors inserting rows into staging table: {errors}")
                continue

            # Construct and execute the MERGE statement
            merge_sql = f"""
            MERGE `{project_id}.{dataset_id}.{table_id}` T
            USING `{project_id}.{dataset_id}.{staging_table_id}` S
            ON T.id = S.id
            WHEN MATCHED THEN
                UPDATE SET T.name = S.name, T.value = S.value
            WHEN NOT MATCHED THEN
                INSERT (id, name, value) VALUES (id, name, value)
            """

            print("Executing MERGE statement...")
            query_job = client.query(merge_sql)
            query_job.result()

            print(f"Successfully merged data from {file_path} into {table_id}")

        finally:
            client.delete_table(staging_table_ref, not_found_ok=True)
            print(f"Deleted staging table {staging_table_id}")


if __name__ == "__main__":
    process_csv_files()
