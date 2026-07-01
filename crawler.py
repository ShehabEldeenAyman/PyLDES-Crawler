import pyoxigraph
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from datetime import datetime
import io
import constants

less_than_relation = pyoxigraph.NamedNode("https://w3id.org/tree#LessThanRelation")
greater_than_relation = pyoxigraph.NamedNode("https://w3id.org/tree#GreaterThanRelation")
tree_node = pyoxigraph.NamedNode("https://w3id.org/tree#node")
tree_member = pyoxigraph.NamedNode("https://w3id.org/tree#member")
tss_snippet = pyoxigraph.NamedNode("https://w3id.org/tss#snippet")

years_set = set()
months_set = set()
day_set = set()
members_set = set()

objects_store = pyoxigraph.Store()


def fetch_ldes_year(base_url, before_date, after_date):
    response = requests.get(base_url)
    if response.status_code == 200:
        year_store = pyoxigraph.Store()
        year_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
        print(f"Loaded {len(year_store)} triples from {base_url}")
        for s, p, o, g in year_store.quads_for_pattern(None, tree_node, None, None):
            url_string = o.value
            match = re.search(r'(\d{4})\.trig$', url_string) 
            if match:
                actual_year = int(match.group(1))
                # Allow the year folder if it falls within our boundary years (inclusive)
                if after_date.year <= actual_year <= before_date.year:
                    years_set.add(o)
        print(f"Years found: {years_set}")

def fetch_ldes_month(before_date, after_date):
    for year_uri in years_set:
        response = requests.get(year_uri.value)
        if response.status_code == 200:
            year_store = pyoxigraph.Store()
            year_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            for s, p, o, g in year_store.quads_for_pattern(None, tree_node, None, None):
                url_string = o.value
                match = re.search(r'/(\d{4})/(\d{2})/', url_string)
                if match:
                    actual_year = int(match.group(1))
                    actual_month = int(match.group(2))
                    
                    # Create year/month tuples for a flawless range comparison
                    after_tuple = (after_date.year, after_date.month)
                    before_tuple = (before_date.year, before_date.month)
                    current_tuple = (actual_year, actual_month)
                    
                    # Python natively handles tuple comparison chronologically:
                    # (2025, 1) <= (2025, 9) <= (2026, 1) -> True
                    if after_tuple <= current_tuple <= before_tuple:
                        months_set.add(o)
    print(f"Months found: {months_set}")

def fetch_ldes_day(before_date, after_date):
    for month_uri in months_set:
        response = requests.get(month_uri.value)
        if response.status_code == 200:
            month_store = pyoxigraph.Store()
            month_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            
            for s, p, o, g in month_store.quads_for_pattern(None, tree_node, None, None):
                url_string = o.value
                
                # Regex looks for /YYYY/MM/DD in the URL path
                match = re.search(r'/(\d{4})/(\d{2})/(\d{2})', url_string)
                
                if match:
                    actual_year = int(match.group(1))
                    actual_month = int(match.group(2))
                    actual_day = int(match.group(3))
                    
                    # Create 3-element tuples for explicit date-range matching
                    after_tuple = (after_date.year, after_date.month, after_date.day)
                    before_tuple = (before_date.year, before_date.month, before_date.day)
                    current_tuple = (actual_year, actual_month, actual_day)
                    
                    # Chronological comparison: checks year -> month -> day sequentially
                    if after_tuple <= current_tuple <= before_tuple:
                        day_set.add(o)
                        
    print(f"Days found: {day_set}")

# def fetch_ldes_members():
#     for day_uri in day_set:
#         response = requests.get(day_uri.value)
#         if response.status_code == 200:
#             day_store = pyoxigraph.Store()
#             day_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            
#             # 1. Search for 'tree_member' as the predicate
#             for s, p, member_uri, g in day_store.quads_for_pattern(None, tree_member, None, None):
#                 # 2. Add the OBJECT (member_uri), not the subject
#                 members_set.add(member_uri)
#                 print(f"Member found: {member_uri}")
                
#             # 3. Fetch quads for each member found
#             for subject in members_set:
#                 for s, p, o, g in day_store.quads_for_pattern(subject, None, None, None):
#                     quad = pyoxigraph.Quad(s, p, o, pyoxigraph.DefaultGraph())
#                     objects_store.add(quad)
#                     #print(f"Quad added: {quad}")

#                 print(f"Object: {o}")

def _fetch_single_day_worker(day_uri):
    """
    Worker function executed by individual threads.
    Downloads a single day's payload, isolates its members, 
    and extracts their associated quads completely in-memory.
    """
    local_members = []
    local_quads = []
    
    try:
        response = requests.get(day_uri.value)
        if response.status_code == 200:
            # Create an isolated, thread-safe memory store for this specific file
            day_store = pyoxigraph.Store()
            day_store.load(response.content, format=pyoxigraph.RdfFormat.TRIG)
            
            # 1. Find all members belonging to this day
            for s, p, member_uri, g in day_store.quads_for_pattern(None, tree_member, None, None):
                local_members.append(member_uri)
                
            # 2. Extract quads for the members found within this day's store
            for subject in local_members:
                for s, p, o, g in day_store.quads_for_pattern(subject, None, None, None):
                    quad = pyoxigraph.Quad(s, p, o, pyoxigraph.DefaultGraph())
                    local_quads.append(quad)
                    
    except Exception as e:
        print(f"Error processing day URI {day_uri.value}: {e}")
        
    return local_members, local_quads


def fetch_ldes_members():
    print(f"Starting concurrent fetch for {len(day_set)} day URIs...")
    
    # Adjust max_workers based on how many parallel network requests you want to allow
    max_workers = 10 
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all day URIs to the thread pool
        future_to_day = {
            executor.submit(_fetch_single_day_worker, day_uri): day_uri 
            for day_uri in day_set
        }
        
        # Collect results as each thread finishes its network I/O
        for future in as_completed(future_to_day):
            day_uri = future_to_day[future]
            try:
                day_members, extracted_quads = future.result()
                
                # Safely update global/outer collections in the main thread.
                # This completely avoids thread conflicts or lock contention.
                for member in day_members:
                    members_set.add(member)
                    print(f"Member found: {member}")
                    
                for quad in extracted_quads:
                    objects_store.add(quad)
                    
            except Exception as e:
                print(f"Day URI {day_uri.value} generated an exception: {e}")
                
    print(f"Concurrent synchronization finished. Accumulated {len(objects_store)} total triples.")

def clear_triplestore():
    """Removes the entire named graph from Virtuoso."""
    params = {'graph-uri': constants.GRAPH_URI}
    
    try:
        print(f"Attempting to delete graph: {constants.GRAPH_URI}...")
        response = requests.delete(
            constants.VIRTUOSO_URL,
            params=params,
            auth=constants.AUTH
        )
        
        # 200 (OK) or 204 (No Content) usually indicates success
        if response.status_code in [200, 204]:
            print(f"Successfully deleted graph: {constants.GRAPH_URI}")
            return True
        else:
            print(f"Failed to delete graph. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"An error occurred during deletion: {e}")
        return False

def verify_triplestore():
    # SPARQL query to count all triples in your specific named graph
    sparql_query = f"""
    SELECT (COUNT(*) AS ?triplesCount)
    WHERE {{
        GRAPH <{constants.GRAPH_URI}> {{
            ?subject ?predicate ?object .
        }}
    }}
    """
    
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.post(
            constants.SPARQL_ENDPOINT, 
            data={'query': sparql_query}, 
            headers=headers, 
            auth=constants.AUTH
        )
        
        if response.status_code == 200:
            results = response.json()
            # Extract the count from the JSON response binding
            count = results['results']['bindings'][0]['triplesCount']['value']
            print(f"Verification Successful!")
            print(f"Total triples inside graph <{constants.GRAPH_URI}>: {count}")
        else:
            print(f"Could not verify. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"An error occurred during verification: {e}")

def dump_graph_file():
    print(f"Dumping {len(objects_store)} triples to {constants.filename}...")

    with open(constants.filename, "wb") as f:
        objects_store.dump(
            output=f,
            format=pyoxigraph.RdfFormat.TURTLE,
            from_graph=pyoxigraph.DefaultGraph(),
        )

    print("Dump complete.")

def upload_graph_triplestore():
    # 1. Prepare parameters and headers
    params = {'graph-uri': constants.GRAPH_URI}
    headers = {'Content-Type': 'text/turtle'}
    print(f"started uploading data to {constants.GRAPH_URI}")
    try:
        # 2. Open the file in binary mode and stream it
        with open(constants.filename, 'rb') as f:
            response = requests.post(
                constants.VIRTUOSO_URL, 
                params=params, 
                data=f, 
                headers=headers, 
                auth=constants.AUTH
            )

        # 3. Check result
        if response.status_code in [200, 201, 204]:
            print(f"Successfully uploaded Data to {constants.GRAPH_URI}")
        else:
            print(f"Failed to upload. Status code: {response.status_code}")
            print(f"Response: {response.text}")

    except FileNotFoundError:
        print(f"Error: The file at {constants.filename} was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")




def main():
    before_date = '02-01-2025'
    after_date = '01-01-2025'

    parsed_before_date = datetime.strptime(before_date, '%d-%m-%Y')
    parsed_after_date = datetime.strptime(after_date, '%d-%m-%Y')

    if parsed_after_date > parsed_before_date:
        print("Error: 'after_date' must be earlier than or equal to 'before_date'.")
        return
    

    fetch_ldes_year("https://shehabeldeenayman.github.io/Gent-Terneuzen-canal/conductivity/conductivity.trig", before_date=parsed_before_date, after_date=parsed_after_date) 
    print("/-------------------------------------------------/")
    fetch_ldes_month(before_date=parsed_before_date, after_date=parsed_after_date)
    print("/-------------------------------------------------/")
    fetch_ldes_day(before_date=parsed_before_date, after_date=parsed_after_date)
    print("/-------------------------------------------------/")
    fetch_ldes_members()
    print("/-------------------------------------------------/")
    #print(objects_store)
    clear_triplestore()
    #push_to_triplestore()
    dump_graph_file()
    #upload_graph_triplestore()
    verify_triplestore()
    



if __name__=="__main__":
    main()