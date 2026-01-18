from flask import Flask, render_template, request, jsonify, session, redirect, url_for #, send_file
from werkzeug.utils import secure_filename # for secure file names
import pandas as pd # for Excel handling
import os # for file system operations
from collections import defaultdict, deque # for data structures
import shutil # for file operations
import re # for regex operations
from reportlab.lib.pagesizes import letter, A4, landscape # for PDF generation
from reportlab.lib.utils import ImageReader # for image handling
from reportlab.pdfgen import canvas # for PDF generation
from io import BytesIO # for in-memory file operations
import base64 # for encoding images

app = Flask(__name__) # Flask app initialization
app.secret_key = 'keyyyy' # Secret key for session management
app.config['UPLOAD_FOLDER'] = 'uploads' # Folder to store uploaded files
app.config['TEMP_FOLDER'] = 'temp_uploads' # Temporary folder for session files

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) # Ensure upload folder exists
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True) # Ensure temp folder exists

# ----------------- Globals -----------------
# parameters_list now contains ABBREVIATIONS (what shows in dropdown)
parameters_list = []  # used by dropdown: ONLY abbreviations
parameter_relations = {}  # key: ABBREVIATION (col D), value: list of related ABBREVIATIONS (from col P)
uml_data = defaultdict(lambda: {
    "attributes": [],
    "relationships": set(),
    "multiplicities": {}
}) # UML data structure

# NEW: mappings for Option A
abbrev_to_param = {}   # abbrev -> Full Parameter Name (col C)
param_to_abbrev = {}   # Full Parameter Name -> abbrev (col D)

# Maximum attributes to show before "View More"
MAX_VISIBLE_ATTRIBUTES = 10


# ----------------- Helpers -----------------
def sanitize_for_mermaid(text):
    if not text: 
        return "" # handle None or empty
    text = str(text).strip() # convert to string and trim
    text = text.replace('"', "'") # replace double quotes with single quotes
    text = text.replace('<', '&lt;')  # escape HTML special chars
    text = text.replace('>', '&gt;') # escape HTML special chars
    text = ' '.join(text.split()) # collapse multiple spaces
    return text


def create_safe_node_id(class_name): # create safe node IDs for mermaid
    safe_id = re.sub(r'[^a-zA-Z0-9]', '_', class_name) # replace non-alphanum with _
    safe_id = re.sub(r'\+', '', safe_id) # remove plus signs
    safe_id = safe_id.strip('_') # trim leading/trailing underscores
    return safe_id if safe_id else 'node' # fallback


def parse_related_cell(cell_value): # Parse Column P cell into list of abbreviations
    """
    Parse a cell from Column P and return a list of abbreviations.
    - Items separated by ';'
    - Each item can be like 'ABBR::public' -> strip '::...' suffix
    """
    out = [] # output list
    if pd.isna(cell_value): # handle NaN
        return out 
    s = str(cell_value).strip() # convert to string and trim
    if not s: 
        return out # empty cell
    parts = [p.strip() for p in s.split(';') if p.strip()] # split by ';' and trim
    for part in parts:
        # remove ::anything suffix (e.g. ::public)
        cleaned = re.sub(r'\s*::\s*.*$', '', part, flags=re.IGNORECASE).strip() # strip again
        if cleaned: # only add non-empty
            out.append(cleaned) # add to output
    return out


# --------- Parameter Relation Finder ---------
def detect_header(df, search_columns): #  detect header row
    """Auto-detect header row by looking for keywords""" 
    for i in range(min(10, len(df))): # check first 10 rows
        row = df.iloc[i].astype(str).str.lower() # convert to lowercase strings
        # if any search keyword appears anywhere in that row
        if any(keyword.lower() in " ".join(row.values) for keyword in search_columns): # found header
            return i # return header row index
    return 0 # default to first row if not found


def load_excel_data(file_paths):
    """
    Load parameter data from multiple Excel files.
    - Column C (index 2) -> Full Parameter Name
    - Column D (index 3) -> Abbreviation (used everywhere for relations)
    - Column P (index 15) -> Related abbreviations list (semicolon-separated, may have ::public)
    - parameters_list will contain abbreviations
    - parameter_relations: abbrev -> list of related abbrevs
    - also populate abbrev_to_param and param_to_abbrev
    """
    global parameters_list, parameter_relations, abbrev_to_param, param_to_abbrev # reset globals
    parameters_list = [] # abbreviations for dropdown
    parameter_relations = {} # abbrev -> list of related abbrevs
    abbrev_to_param = {} # abbrev -> Full Parameter Name
    param_to_abbrev = {} # Full Parameter Name -> abbrev

    try:
        for file_path in file_paths:
            # read all sheets, no header so we can detect header row manually
            try:
                df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl', header=None) # no header
            except Exception:
                # fallback to default read if any issue
                df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl') # default read

            for sheet_name, df in df_sheets.items(): 
                # skip tiny sheets
                if df.shape[1] < 16: # must have at least 16 columns
                    continue

                # detect header row heuristically
                header_row = detect_header(df, search_columns=["Parameter", "Parameter Name", "Abbreviation", "Relation", "Related"]) # detect header
                df.columns = df.iloc[header_row] # set header
                df = df.iloc[header_row + 1:].reset_index(drop=True) # data below header

                # Column indexes according to your request:
                # C -> index 2, D -> index 3, P -> index 15
                try:
                    col_full = df.columns[2]   # Column C (Full Parameter Name)
                    col_abbr = df.columns[3]   # Column D (Abbreviation)
                    col_rel = df.columns[15]   # Column P (Related list)
                except Exception:
                    # If headers messed up, skip this sheet
                    continue

                df_clean = df.dropna(subset=[col_full], how='all') # drop rows without full name

                for _, row in df_clean.iterrows(): # iterate rows
                    full_name = str(row[col_full]).strip() if pd.notna(row[col_full]) else "" # full name
                    abbrev = str(row[col_abbr]).strip() if pd.notna(row[col_abbr]) else "" # abbreviation
                    related_cell = row[col_rel] if col_rel in df.columns else "" # related cell

                    # If abbreviation is empty, fallback to a cleaned form of full_name
                    if not abbrev or abbrev.lower() in ['nan', 'none']: # generate from full name
                        abbrev = re.sub(r'\s+', '_', full_name).strip() if full_name else "" # replace spaces with underscores

                    if not full_name: 
                        # skip rows without a full name
                        continue

                    # register mappings
                    if abbrev:
                        abbrev_to_param[abbrev] = full_name # map abbrev to full name
                        # keep first abbreviation if multiple map to same full name; prefer abbrev
                        if full_name not in param_to_abbrev:
                            param_to_abbrev[full_name] = abbrev # map full name to abbrev
                    else:
                        # no abbrev: still add mapping keyed by generated abbrev
                        continue

                    # add to dropdown list (unique)
                    if abbrev and abbrev not in parameters_list:
                        parameters_list.append(abbrev) # add abbrev to list

                    # parse relations from Column P (convert to abbrev list)
                    rels = parse_related_cell(related_cell)
                    # sanitize and dedupe
                    rels = [r for r in [x.strip() for x in rels] if r and r.lower() not in ['nan', 'none', '']] # sanitize
                    if rels: # if there are related abbreviations
                        existing = parameter_relations.get(abbrev, []) # existing relations
                        combined = list(set(existing + rels)) # combine and dedupe
                        parameter_relations[abbrev] = combined # update with combined list
                    else:
                        # ensure the key exists with empty list rather than a string
                        if abbrev not in parameter_relations: 
                            parameter_relations[abbrev] = [] # empty list

        # sort dropdown alphabetically and keep unique
        parameters_list = sorted(list(set(parameters_list))) 

    except Exception as e: # log any error
        print(f"Failed to load Excel: {e}") # log error


# --------- UML Diagram Generator (UNCHANGED) ---------
def load_uml_data(file_paths):
    """Load UML data from multiple Excel files"""
    global uml_data # reset UML data
    uml_data.clear() # reset UML data
    all_classes = set() # set of all class names

    try:
        for file_path in file_paths: # process each file
            if not os.path.exists(file_path): # skip missing files
                continue

            df = pd.read_excel(file_path, sheet_name=None, engine='openpyxl') # read all sheets

            for sheet in df: # process each sheet
                data = df[sheet] # get sheet data
                if data.shape[1] < 31: # must have at least 31 columns
                    continue

                data = data.rename(columns={
                    data.columns[1]: "MOC_Name", # Column B
                    data.columns[2]: "Parameter_Name", # Column C
                    data.columns[3]: "Abbreviation", # Column D
                    data.columns[4]: "Data_Type", # Column E
                    data.columns[5]: "Parent_Parameter", # Column F
                    data.columns[25]: "Required_On_Creation", # Column Z
                    data.columns[27]: "Required_On_Creation_Col_AB", # Column AB
                    data.columns[28]: "Modification", # Column AC
                    data.columns[29]: "MinOccurs", # Column AD
                    data.columns[30]: "MaxOccurs" # Column AE
                }) # rename relevant columns

                data = data.dropna(subset=["MOC_Name", "Parameter_Name"], how='all') # drop rows without class or param name

                for _, row in data.iterrows(): # iterate rows
                    class_name = str(row["MOC_Name"]).strip() # class name
                    param_name = str(row["Parameter_Name"]).strip() # parameter name
                    abbreviation = str(row["Abbreviation"]).strip() if pd.notna(row["Abbreviation"]) else param_name # abbrev fallback
                    data_type = str(row["Data_Type"]).strip() # data type
                    mod_status = str(row["Modification"]).strip().lower() # modification status
                    required = str(row["Required_On_Creation"]).strip().lower() # required status
                    required_col_ab = str(row["Required_On_Creation_Col_AB"]).strip().lower() if pd.notna(row["Required_On_Creation_Col_AB"]) else required # required col AB
                    parent = str(row["Parent_Parameter"]).strip() if pd.notna(row["Parent_Parameter"]) else None # parent param
                    min_occurs = str(row["MinOccurs"]).strip() if pd.notna(row["MinOccurs"]) else "" # min occurs
                    max_occurs = str(row["MaxOccurs"]).strip() if pd.notna(row["MaxOccurs"]) else ""  # max occurs

                    if (param_name.lower() == "parameter name" or # skip header rows
                        class_name.lower() in ['nan', 'none', ''] or # skip invalid
                        param_name.lower() in ['nan', 'none', ''] or # skip invalid
                        not class_name or not param_name or # skip empty
                        class_name == 'nan' or param_name == 'nan'): 
                        continue

                    if "bts" in mod_status:
                        color = "red" # red for BTS
                    elif "on-line" in mod_status:
                        color = "green" # green for on-line
                    elif "not modifiable" in mod_status:
                        color = "gray" # gray for not modifiable
                    else:
                        color = "black" # default black

                    if "mandatory" in required_col_ab:
                        mand = "(M)" # mandatory
                    elif "optional" in required_col_ab:
                        mand = "(O)" # optional
                    elif "system" in required_col_ab or "value set by" in required_col_ab:
                        mand = "(S)" # system
                    else:
                        mand = "" # unknown

                    uml_data[class_name]["attributes"].append({
                        "name": abbreviation, # parameter name
                        "type": data_type, # data type
                        "mandatory": mand, # mandatory status
                        "color": color, # color based on mod status
                        "parent": parent # parent parameter
                    }) # add attribute to class

                    if "/" in class_name:
                        parts = class_name.split("/") # split by '/'
                        for i in range(1, len(parts)):
                            parent_class = "/".join(parts[:i]) # parent class
                            child_class = "/".join(parts[:i + 1]) # child class
                            uml_data[parent_class]["relationships"].add(child_class) # add relationship

                            multiplicity = "" # default multiplicity
                            if min_occurs and min_occurs.lower() != 'nan' and max_occurs and max_occurs.lower() != 'nan': # both present
                                multiplicity = f"{min_occurs}..{max_occurs}" # both
                            elif min_occurs and min_occurs.lower() != 'nan': # only min present
                                multiplicity = f"{min_occurs}..*" # min to many
                            elif max_occurs and max_occurs.lower() != 'nan': # only max present
                                multiplicity = f"0..{max_occurs}" # zero to max

                            if multiplicity:
                                uml_data[parent_class]["multiplicities"][child_class] = multiplicity # set multiplicity

                    all_classes.add(class_name) # add to all classes set

        return sorted(all_classes) # return sorted list of all classes
    except Exception as e:
        print(f"Error loading UML data: {e}") # log error
        return []


# ----------------- Routes: Parameter UI -----------------
@app.route('/parameter.html') # Parameter UI route
def parameter_page():
    if 'uploaded_files' not in session or not session['uploaded_files']: # check session
        return redirect(url_for('landing_page')) # redirect if no files
    return render_template('parameter.html') # render parameter page


@app.route('/get-parameters') # Get parameters route
def get_parameters():  
    try:
        # Return abbreviations (parameters_list)
        if not parameters_list:
            return jsonify({
                "error": "No parameters loaded. Upload an Excel file first.",
                "parameters": []
            }), 500 # error if empty
        return jsonify({"parameters": parameters_list}) # return parameters
    except Exception as e:
        return jsonify({"error": str(e), "parameters": []}), 500 # error handling


@app.route('/get-relation', methods=['POST'])
def get_relation():
    """
    DEPENDENT (forward):
        Row where Column D == P → Column P contains dependent parameters.
        Uses BFS with dependent_depth.

    DEPENDENCY (backward):
        Row where cleaned P contains P → Column D is a dependency.
        ALWAYS direct — no depth, no recursion.

    INDIRECT:
        Start from (direct dependents ∪ direct dependencies).
        For indirect_depth loops:
            For each X in frontier:
                add direct dependents(X)
                add direct dependencies(X)
    """
    try:
        data = request.get_json() # get JSON data

        P = data.get("parameter", "").strip() # parameter to analyze
        dependent_depth = int(data.get("dependent_depth", 1)) # depth for dependents
        indirect_depth = int(data.get("indirect_depth", 1)) # depth for indirect

        if not P:
            return jsonify({"error": "No parameter provided"}), 400 # error if no parameter

        file_paths = session.get('uploaded_files', []) # get uploaded files from session
        if not file_paths:
            return jsonify({"error": "No Excel files uploaded"}), 400 # error if no files

        # Final output sets
        dependent_set = set() # direct dependents
        dependency_set = set() # direct dependencies
        indirect_set = set() # indirect relations

        # --- Column P cleaner ---(relates parameter column)
        def extract_related(cell):
            if pd.isna(cell):
                return [] ## handle NaN
            s = str(cell).strip()
            if not s:
                return [] # empty cell
            items = [] # output list
            for part in s.split(";"): # split by ';'
                part = part.strip() # trim whitespace
                if not part:
                    continue
                part = re.sub(r"::.*$", "", part)     # remove ::public etc.
                if "-" in part:
                    part = part.split("-")[-1].strip() # take part after last '-'
                if part:
                    items.append(part) # add to list
            return items # return list of related parameters

        # ---------------- PROCESS ALL FILES ----------------
        for excel_path in file_paths:

            df = pd.read_excel(excel_path, engine='openpyxl') # read Excel file
            if df.shape[1] < 16:   # must have at least 16 columns
                continue

            col_D = df.columns[3] # Column D(abbreviation)
            col_P = df.columns[15] # Column P(related list)

            df["_P_clean"] = df[col_P].apply(extract_related) # pre-cleaned Column P

            # =====================================================
            # 1️⃣ DIRECT DEPENDENT (forward)
            # =====================================================
            direct_dependents = set() # direct dependents set
            rows = df[df[col_D].astype(str).str.strip() == P][col_P] # rows where D == P(column abbreviation==related parameter)

            for val in rows:
                direct_dependents |= set(extract_related(val)) # add direct dependents

            # BFS using dependent_depth
            visited = {P} # visited set
            frontier = {P} # initial frontier

            for _ in range(dependent_depth): # for each depth level
                new_frontier = set() # next frontier
                for param in frontier: # for each parameter in frontier
                    rows2 = df[df[col_D].astype(str).str.strip() == param][col_P] # find rows where D == param(column abbreviation==parameter)
                    for v in rows2:
                        for dep in extract_related(v):# extract related
                            if dep not in visited: # if not visited
                                visited.add(dep) # mark visited
                                dependent_set.add(dep) # add to dependent set
                                new_frontier.add(dep) # add to new frontier
                if not new_frontier: # no more to explore
                    break
                frontier = new_frontier # update frontier

            # 2️⃣ DIRECT DEPENDENCY (backward NO DEPTH)
            rows2 = df[df["_P_clean"].apply(lambda arr: P in arr)][col_D] # rows where cleaned P contains P(related parameter)(column abbreviation)

            for val in rows2: # for each value
                cleaned = str(val).strip() # clean value
                if cleaned: # if not empty
                    dependency_set.add(cleaned) # add to dependency set

            # 3️⃣ INDIRECT = BFS using indirect_depth
            # =====================================================
            start_points = direct_dependents | dependency_set # start from direct dependents and dependencies

            visited_indirect = set(start_points) # visited set for indirect
            frontier_indirect = set(start_points) # initial frontier for indirect

            for _ in range(indirect_depth): # for each indirect depth level
                next_frontier = set() # next frontier
                for X in frontier_indirect: # for each parameter in frontier

                    # dependents of X
                    rowsX = df[df[col_D].astype(str).str.strip() == X][col_P] # rows where D == X(column abbreviation==parameter)
                    for v in rowsX: # for each value
                        for dep in extract_related(v): # extract related
                            if dep not in visited_indirect: # if not visited
                                visited_indirect.add(dep) # mark visited
                                indirect_set.add(dep) # add to indirect set
                                next_frontier.add(dep) # add to next frontier

                    # dependencies of X
                    rowsX2 = df[df["_P_clean"].apply(lambda arr: X in arr)][col_D] # rows where cleaned P contains X(related parameter)(column abbreviation)
                    for v in rowsX2: # for each value
                        cleaned = str(v).strip() # clean value
                        if cleaned and cleaned not in visited_indirect: # if not visited
                            visited_indirect.add(cleaned) # mark visited
                            indirect_set.add(cleaned) # add to indirect set
                            next_frontier.add(cleaned) # add to next frontier

                if not next_frontier: # no more to explore
                    break

                frontier_indirect = next_frontier # update frontier

        # Final cleanup
        indirect_set -= dependent_set # remove direct dependents
        indirect_set -= dependency_set # remove direct dependencies
        indirect_set.discard(P) # remove P itself if present

        return jsonify({
            "dependent": sorted(dependent_set), 
            "dependency": sorted(dependency_set), 
            "indirect": sorted(indirect_set) 
        }) # return results

    except Exception as e:
        return jsonify({"error": str(e)}), 500 # error handling



@app.route('/reload-data', methods=['POST']) # Reload data route
def reload_data(): # Reload parameter data from session files
    try:
        file_paths = session.get('uploaded_files', []) # get uploaded files from session
        if not file_paths: 
            return jsonify({"success": False, "error": "No files uploaded"}), 400 # error if no files

        load_excel_data(file_paths) # reload data
        return jsonify({ 
            "success": True, # success message
            "message": f"Data reloaded. Found {len(parameters_list)} abbreviations." 
        }) # return success
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


@app.route('/test-data') # Test data route
def test_data():
    file_paths = session.get('uploaded_files', []) # get uploaded files from session
    return jsonify({
        "parameters_count": len(parameters_list), # count of parameters(abbreviations)
        "relations_count": len(parameter_relations), # count of relations(abbrev -> related abbrevs)
        "sample_parameters": parameters_list[:5] if parameters_list else [], # sample parameters
        "uploaded_files": file_paths
    }) # return test data


# ----------------- UML UI -----------------
@app.route('/umldiagram.html') # UML UI route
def uml_ui():
    if 'uploaded_files' not in session or not session['uploaded_files']: # check session
        return redirect(url_for('landing_page')) # redirect if no files
    return render_template('umldiagram.html') # render UML page


@app.route('/upload-main', methods=['POST']) # Upload from main page
def upload_main():
    """Handle file upload from main page and store in session"""
    try:
        uploaded_files = request.files.getlist("excel_files") # get uploaded files
        diagram_type = request.form.get('diagram_type', 'uml') # get diagram type
        available_files = request.form.getlist('available_files') # get selected available files

        if not uploaded_files and not available_files:
            return jsonify({"success": False, "error": "No files selected"}), 400 # error if no files

        if 'session_id' not in session: # create unique session ID
            import uuid # unique ID
            session['session_id'] = str(uuid.uuid4()) # store in session

        session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id']) # session temp dir
        os.makedirs(session_dir, exist_ok=True) # ensure session dir exists
        file_paths = [] # list of file paths

        # Process newly uploaded files
        for file in uploaded_files:
            if file and file.filename.endswith(('.xlsx', '.xls', '.xlsm')): # check extension
                filename = secure_filename(file.filename) # secure filename
                file_path = os.path.join(session_dir, filename) # session file path
                file.save(file_path) # save file
                file_paths.append(file_path) # add to list
                # Copy to global uploads folder for listing
                global_path = os.path.join(app.config['UPLOAD_FOLDER'], filename) # global upload path
                shutil.copy2(file_path, global_path) # copy to uploads folder

        # Process selected available files (copy to session)
        for filename in available_files:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')): # check extension
                safe_filename = secure_filename(filename) # secure filename
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename) # source path
                if os.path.exists(source_path): # check existence
                    dest_path = os.path.join(session_dir, safe_filename) # dest path
                    shutil.copy2(source_path, dest_path) # copy to session dir
                    file_paths.append(dest_path) # add to list

        if not file_paths:
            return jsonify({"success": False, "error": "No valid Excel files found"}), 400 # error if no valid files

        session['uploaded_files'] = file_paths # store file paths in session
        session['diagram_type'] = diagram_type # store diagram type in session

        # Load data based on diagram type
        if diagram_type == 'uml': # UML diagram
            load_uml_data(file_paths) # Load UML data
            load_excel_data(file_paths)  # Also load parameter data with ALL files
            return jsonify({"success": True, "redirect": url_for('uml_ui')}) # redirect to UML page
        else:
            load_excel_data(file_paths) # Load parameter data
            return jsonify({"success": True, "redirect": url_for('parameter_page')}) # redirect to parameter page

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


@app.route('/select-available-files', methods=['POST']) # Select available files route
def select_available_files(): 
    """Handle selection of available files without upload"""
    try:
        data = request.get_json() # get JSON data
        selected_filenames = data.get('filenames', []) # get selected filenames
        diagram_type = data.get('diagram_type', 'uml') # get diagram type

        if not selected_filenames:
            return jsonify({"success": False, "error": "No files selected"}), 400 # error if no files

        if 'session_id' not in session:
            import uuid # unique ID
            session['session_id'] = str(uuid.uuid4()) # store in session

        session_dir = os.path.join(app.config['TEMP_FOLDER'], session['session_id']) # session temp dir
        os.makedirs(session_dir, exist_ok=True) # ensure session dir exists
        file_paths = [] # list of file paths

        # Copy selected files to session directory
        for filename in selected_filenames:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')):
                safe_filename = secure_filename(filename) # secure filename
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename) # source path
                if os.path.exists(source_path):
                    dest_path = os.path.join(session_dir, safe_filename) # dest path
                    shutil.copy2(source_path, dest_path) # copy to session dir
                    file_paths.append(dest_path) # add to list

        if not file_paths:
            return jsonify({"success": False, "error": "No valid files found"}), 400 # error if no valid files

        session['uploaded_files'] = file_paths # store file paths in session
        session['diagram_type'] = diagram_type # store diagram type in session

        if diagram_type == 'uml':
            load_uml_data(file_paths) # load UML data
            load_excel_data(file_paths) # also load parameter data with ALL files
            return jsonify({
                "success": True,
                "message": "Files loaded successfully.",
                "redirect": "/umldiagram.html"
            }) # redirect to UML page
        else:
            load_excel_data(file_paths) # load parameter data
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(parameters_list)} abbreviations.",
                "redirect": "/parameter.html"
            }) # redirect to parameter page
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


# ----------------- Uploads to /uploads -----------------
@app.route('/upload-to-folder', methods=['POST']) # Upload to uploads folder route
def upload_to_folder():
    """Handle file uploads to the uploads folder from the plus button"""
    try:
        uploaded_files = request.files.getlist("files") # get uploaded files

        if not uploaded_files:
            return jsonify({"success": False, "error": "No files uploaded"}), 400 # error if no files

        upload_folder = app.config['UPLOAD_FOLDER'] # upload folder
        os.makedirs(upload_folder, exist_ok=True) # ensure upload folder exists

        uploaded_count = 0 # count of uploaded files
        for file in uploaded_files: # process each file
            if file and file.filename.endswith(('.xlsx', '.xls', '.xlsm')): # check extension
                filename = secure_filename(file.filename) # secure filename
                file_path = os.path.join(upload_folder, filename) # file path
                file.save(file_path) # save file
                uploaded_count += 1 # increment count

        if uploaded_count == 0: # no valid files uploaded
            return jsonify({"success": False, "error": "No valid Excel files found"}), 400 # error if no valid files

        return jsonify({
            "success": True,
            "message": f"{uploaded_count} file(s) uploaded successfully"
        }) # return success
    except Exception as e:
        print(f"Error uploading files: {e}") # log error 
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


@app.route('/delete-all-files', methods=['DELETE']) # Delete all files route
def delete_all_files():
    """Delete all files from the uploads folder"""
    try:
        upload_folder = app.config['UPLOAD_FOLDER'] # upload folder
        if not os.path.exists(upload_folder): # check existence
            return jsonify({"success": False, "error": "Upload folder not found"}), 404 # folder not found

        deleted_count = 0 # count of deleted files
        for filename in os.listdir(upload_folder): # iterate files
            file_path = os.path.join(upload_folder, filename) # file path
            if os.path.isfile(file_path) and filename.lower().endswith(('.xls', '.xlsx', '.xlsm')):   # check file type
                os.remove(file_path) # delete file
                deleted_count += 1 # increment count

        return jsonify({
            "success": True,
            "message": f"{deleted_count} file(s) deleted successfully"
        }) # return success
    except Exception as e:
        print(f"Error deleting all files: {e}") # log error
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


@app.route('/delete-file', methods=['DELETE']) # Delete single file route
def delete_file():
    """Delete a single file from the uploads folder"""
    try:
        data = request.get_json() # get JSON data
        filename = data.get('filename') # get filename to delete

        if not filename:
            return jsonify({"success": False, "error": "No filename provided"}), 400 # error if no filename

        safe_filename = secure_filename(filename) # sanitize filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename) # construct file path

        if not os.path.exists(file_path):
            return jsonify({"success": False, "error": "File not found"}), 404 # file not found

        if not safe_filename.lower().endswith(('.xls', '.xlsx', '.xlsm')): # validate file type
            return jsonify({"success": False, "error": "Invalid file type"}), 400 # validate file type

        os.remove(file_path) # delete file

        return jsonify({
            "success": True,
            "message": f"File '{safe_filename}' deleted successfully"
        }) # return success
    except Exception as e:
        print(f"Error deleting file: {e}") # log error
        return jsonify({"success": False, "error": str(e)}), 500 # error handling


# ----------------- UML class loading for UI -----------------
@app.route('/upload', methods=['POST']) # Upload UML classes route
def upload_file(): 
    """Handle UML diagram generation using session files"""
    global uml_data # access global UML data

    file_paths = session.get('uploaded_files', []) # get uploaded files from session
    if not file_paths:
        return jsonify({
            "success": False,
            "error": "No files found in session. Please upload files from the main page."
        }), 400 # error if no files

    # If UML data not already loaded, load it
    if not uml_data:
        classes = load_uml_data(file_paths) # load UML data
        classes_data = [{"value": cls, "label": cls.split("/")[-1]} for cls in classes] # prepare class data
        classes_with_all = [{"value": "All Classes", "label": "All Classes"}] + classes_data # prepend All Classes
        return jsonify({"success": True, "classes": classes_with_all}) # return classes

    else:
        all_classes = sorted(uml_data.keys()) # get all class names
        classes_data = [{"value": cls, "label": cls.split("/")[-1]} for cls in all_classes] # prepare class data
        classes_with_all = [{"value": "All Classes", "label": "All Classes"}] + classes_data # prepend All Classes
        return jsonify({"success": True, "classes": classes_with_all}) # return classes


# ----------------- UML Diagram Generation -----------------
@app.route('/uml', methods=['POST']) # UML generation route
def generate_uml():
    data = request.get_json() # get JSON data
    selected_class = data.get("parameter") # selected class
    depth = int(data.get("depth", 1)) # depth for relationships

    if not selected_class:
        return jsonify({"uml": "graph TD\n%% No class selected", "class_count": 0}) # no class selected

    if selected_class == "All Classes": # generate UML for all classes
        return generate_all_classes_uml() # Generate UML for all classes

    if selected_class not in uml_data: 
        return jsonify({"uml": "graph TD\n%% Invalid class selected", "class_count": 0}) # invalid class

    visited = set() # visited classes
    result_classes = {} # classes to include in UML
    queue = deque() # BFS queue
    queue.append((selected_class, 0)) # (class, current_depth)

    while queue:
        current_cls, current_depth = queue.popleft() # dequeue
        if current_cls in visited or current_depth > depth: 
            continue

        visited.add(current_cls) # mark visited
        result_classes[current_cls] = uml_data[current_cls] # add class info

        if current_depth < depth: # only explore further if within depth
            for rel in uml_data[current_cls]["relationships"]: # for each related class
                queue.append((rel, current_depth + 1))# enqueue related classes

    lines = ["graph TD"] # start graph

    for cls, info in result_classes.items(): # for each class
        safe_cls = create_safe_node_id(cls) # safe node ID
        display_name = sanitize_for_mermaid(cls.split("/")[-1]) # display name
        
        # Center-aligned class name
        label_lines = [f"<div style='text-align:center;'><b>{display_name}</b></div>", "<hr>"] # center-aligned class name

        attributes = info["attributes"] # all attributes
        visible_attrs = attributes[:MAX_VISIBLE_ATTRIBUTES] # visible attributes
        hidden_count = len(attributes) - MAX_VISIBLE_ATTRIBUTES # count of hidden attributes

        # Left-aligned attributes with padding
        for attr in visible_attrs:
            attr_name = sanitize_for_mermaid(attr['name']) # add attribute line
            attr_type = sanitize_for_mermaid(attr['type'])  # add attribute line
            attr_mand = sanitize_for_mermaid(attr['mandatory']) # add attribute line
            if not attr_name or attr_name == 'nan': 
                continue # skip invalid
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:{attr['color']}'>+ {attr_name} : {attr_type} {attr_mand}</span></div>") # add attribute line

        if hidden_count > 0:# indicate more
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:#3b82f6;font-weight:600;font-style:italic'>... +{hidden_count} more attributes</span></div>") # indicate more

        html_label = "<br>".join(label_lines).replace('"', '#quot;') # sanitize quotes
        lines.append(f'{safe_cls}["{html_label}"]') # add class node

    for cls, info in result_classes.items(): # for each class
        from_cls = create_safe_node_id(cls) # source class
        for rel in info["relationships"]:# for each relationship
            if rel in result_classes:
                to_cls = create_safe_node_id(rel) # target class
                multiplicity = info["multiplicities"].get(rel, "") # get multiplicity
                if multiplicity:
                    multiplicity = sanitize_for_mermaid(multiplicity) # sanitize multiplicity
                    lines.append(f'{from_cls} -->|{multiplicity}| {to_cls}') # add relationship with multiplicity
                else:
                    lines.append(f"{from_cls} --> {to_cls}") # add relationship

    return jsonify({"uml": "\n".join(lines), "class_count": len(result_classes)}) # return class count

def generate_all_classes_uml(): # Generate UML for all classes
    if not uml_data:
        return jsonify({"uml": "graph TD\n%% No classes available", "class_count": 0}) # no data

    lines = ["graph TD"] # start graph

    for cls, info in uml_data.items(): # for each class
        safe_cls = create_safe_node_id(cls) # safe node ID
        display_name = sanitize_for_mermaid(cls.split("/")[-1]) # display name
        
        # Center-aligned class name
        label_lines = [f"<div style='text-align:center;'><b>{display_name}</b></div>", "<hr>"] # center-aligned class name

        attributes = info["attributes"] # all attributes
        visible_attrs = attributes[:MAX_VISIBLE_ATTRIBUTES] # visible attributes
        hidden_count = len(attributes) - MAX_VISIBLE_ATTRIBUTES # count of hidden attributes

        # Left-aligned attributes with padding
        for attr in visible_attrs:
            attr_name = sanitize_for_mermaid(attr['name']) # add attribute line
            attr_type = sanitize_for_mermaid(attr['type']) # add attribute line
            attr_mand = sanitize_for_mermaid(attr['mandatory']) # add attribute line
            if not attr_name or attr_name == 'nan': # skip invalid
                continue
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:{attr['color']}'>+ {attr_name} : {attr_type} {attr_mand}</span></div>") # add attribute line

        if hidden_count > 0: # indicate more
            label_lines.append(f"<div style='text-align:left;padding-left:8px;'><span style='color:#3b82f6;font-weight:600;font-style:italic'>... +{hidden_count} more attributes</span></div>") # indicate more

        html_label = "<br>".join(label_lines).replace('"', '#quot;') # sanitize quotes
        lines.append(f'{safe_cls}["{html_label}"]') # add class node

    for cls, info in uml_data.items():
        from_cls = create_safe_node_id(cls) # source class
        for rel in info["relationships"]: # for each relationship
            if rel in uml_data:
                to_cls = create_safe_node_id(rel) # target class
                multiplicity = info["multiplicities"].get(rel, "") # get multiplicity
                if multiplicity:
                    multiplicity = sanitize_for_mermaid(multiplicity) # sanitize multiplicity
                    lines.append(f'{from_cls} -->|{multiplicity}| {to_cls}') # add relationship with multiplicity
                else:
                    lines.append(f"{from_cls} --> {to_cls}") # add relationship

    return jsonify({"uml": "\n".join(lines), "class_count": len(uml_data)}) # return total classes

@app.route('/download-pdf', methods=['POST']) # Download UML diagram as PDF
def download_pdf():
    try:
        data = request.get_json() # get JSON data
        image_data = data.get('imageData') # base64 image data
        class_name = data.get('className', 'uml_diagram') # default name
        
        if not image_data:
            return jsonify({"success": False, "error": "No image data provided"}), 400 #400
        
        # Remove data URL prefix if present
        if ',' in image_data:
            image_data = image_data.split(',')[1] # get base64 part
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data) # decode image
        image_buffer = BytesIO(image_bytes) # image buffer
        
        # Create PDF in memory
        pdf_buffer = BytesIO() # PDF buffer
        
        # Use landscape A4 for better diagram visibility
        page_width, page_height = landscape(A4) # landscape A4 dimensions
        
        # Create canvas
        c = canvas.Canvas(pdf_buffer, pagesize=landscape(A4)) # landscape A4
        
        # Get image dimensions
        img = ImageReader(BytesIO(image_bytes)) # read image
        img_width, img_height = img.getSize() # original image size
        
        # Calculate scaling to fit page with margins
        margin = 50 # margin in points
        available_width = page_width - (2 * margin) # available width
        available_height = page_height - (2 * margin) # available height
        
        # Scale image to fit page while maintaining aspect ratio
        scale_width = available_width / img_width # scale width
        scale_height = available_height / img_height # scale height
        scale = min(scale_width, scale_height) # uniform scale factor
        
        scaled_width = img_width * scale # scaled width
        scaled_height = img_height * scale # scaled height
        
        # Center the image on the page
        x = (page_width - scaled_width) / 2 # center horizontally
        y = (page_height - scaled_height) / 2 # center vertically
        
        # Draw the image
        c.drawImage(img, x, y, width=scaled_width, height=scaled_height)# draw image
        
        # Add title at the top
        c.setFont("Helvetica-Bold", 16)# title font
        title = f"UML Class Diagram - {class_name}" # title text
        c.drawCentredString(page_width / 2, page_height - 30, title) # title
        
        # Add timestamp at the bottom
        from datetime import datetime # import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # current timestamp
        c.setFont("Helvetica", 10) # timestamp font
        c.drawCentredString(page_width / 2, 20, f"Generated on {timestamp}") # timestamp
        
        # Save PDF
        c.save() # save PDF
        
        # Get PDF bytes
        pdf_bytes = pdf_buffer.getvalue() # get PDF bytes
        pdf_buffer.close() # close buffer
        
        # Encode to base64 for sending to frontend
        pdf_base64 = base64.b64encode(pdf_bytes).decode('utf-8') # encode to base64
        
        return jsonify({
            "success": True,
            "pdf": pdf_base64,
            "filename": f"uml_diagram_{class_name}.pdf"
        }) #200
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 #500
    
    
# ----------------- Session / Home -----------------
@app.route('/clear-session', methods=['POST']) # Clear session data and temp files
def clear_session(): # Clear session data and temp files
    try:
        if 'session_id' in session: # check session
            folder = os.path.join(app.config['TEMP_FOLDER'], session['session_id']) # session folder
            if os.path.exists(folder): # remove session folder
                shutil.rmtree(folder) # remove session folder

        session.clear() # clear session data
        parameters_list.clear() # reset parameters
        parameter_relations.clear() # reset relations
        uml_data.clear() # reset UML data
        abbrev_to_param.clear() # reset mappings
        param_to_abbrev.clear() # reset mappings

        return jsonify({"success": True, "message": "Session cleared"}) #200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500 #500


@app.route('/') # Landing page
def landing_page():
    return render_template('main.html') # Landing page


@app.route('/get-available-files') # List files in uploads folder
def get_available_files(): # List files in uploads folder
    try: 
        files = [] # output list
        upload_folder = app.config['UPLOAD_FOLDER'] # uploads folder
        if not os.path.exists(upload_folder): # create if missing
            os.makedirs(upload_folder, exist_ok=True) # create if missing

        for filename in os.listdir(upload_folder): # list files
            file_path = os.path.join(upload_folder, filename) # full path
            if os.path.isfile(file_path) and filename.lower().endswith(('.xls', '.xlsx', '.xlsm')): # only Excel files
                files.append({
                    "name": filename,
                    "size": os.path.getsize(file_path)
                }) # add to list
        return jsonify({"success": True, "files": files}) #200
    except Exception as e:
        print(f"Error getting available files: {e}") #500
        return jsonify({"success": False, "files": [], "error": str(e)}) #500


if __name__ == '__main__': # pragma: no cover
    app.run(debug=True) # Set debug=False for production