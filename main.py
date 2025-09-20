from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
import pandas as pd
import os
from collections import defaultdict, deque
import tempfile
import shutil

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['TEMP_FOLDER'] = 'temp_uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['TEMP_FOLDER'], exist_ok=True)

parameters_list = []
parameter_relations = {}
uml_data = defaultdict(lambda: {
    "attributes": [],
    "relationships": set()
})

# --------- Parameter Relation Finder ---------
def load_excel_data(file_path):
    """Load parameter data from a given Excel file"""
    global parameters_list, parameter_relations
    try:
        df_sheets = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')
        parameters_list = []
        parameter_relations = {}
        
        for sheet_name, df in df_sheets.items():
            if df.shape[1] < 30:
                continue
                
            df = df.rename(columns={
                df.columns[1]: "MOC_Name",
                df.columns[2]: "Parameter_Name",
                df.columns[15]: "Related_Parameters"
            })
            
            df_clean = df.dropna(subset=["MOC_Name", "Parameter_Name"], how='all')
            
            for _, row in df_clean.iterrows():
                moc_name = str(row["MOC_Name"]).strip() if pd.notna(row["MOC_Name"]) else ""
                param_name = str(row["Parameter_Name"]).strip() if pd.notna(row["Parameter_Name"]) else ""
                related_params = str(row["Related_Parameters"]).strip() if pd.notna(row["Related_Parameters"]) else ""
                
                if param_name.lower() == "parameter name" or not param_name or param_name.lower() == 'nan':
                    continue
                    
                if param_name not in parameters_list:
                    parameters_list.append(param_name)
                    
                if related_params and related_params.lower() != 'nan':
                    parameter_relations[param_name] = related_params
                else:
                    parameter_relations[param_name] = "No related parameters found"
        
        parameters_list.sort()
    except Exception as e:
        print(f"Failed to load Excel: {e}")

def load_uml_data(file_paths):
    """Load UML data from multiple Excel files"""
    global uml_data
    uml_data.clear()
    all_classes = set()
    
    try:
        for file_path in file_paths:
            if not os.path.exists(file_path):
                continue
                
            df = pd.read_excel(file_path, sheet_name=None, engine='openpyxl')
            
            for sheet in df:
                data = df[sheet]
                if data.shape[1] < 30:
                    continue
                    
                data = data.rename(columns={
                    data.columns[1]: "MOC_Name",
                    data.columns[2]: "Parameter_Name",
                    data.columns[4]: "Data_Type",
                    data.columns[5]: "Parent_Parameter",
                    data.columns[25]: "Required_On_Creation",
                    data.columns[28]: "Modification"
                })
                
                data = data.dropna(subset=["MOC_Name", "Parameter_Name"], how='all')
                
                for _, row in data.iterrows():
                    class_name = str(row["MOC_Name"]).strip()
                    param_name = str(row["Parameter_Name"]).strip()
                    data_type = str(row["Data_Type"]).strip()
                    mod_status = str(row["Modification"]).strip().lower()
                    required = str(row["Required_On_Creation"]).strip().lower()
                    parent = str(row["Parent_Parameter"]).strip() if pd.notna(row["Parent_Parameter"]) else None
                    
                    # Skip invalid entries
                    if (param_name.lower() == "parameter name" or 
                        class_name.lower() in ['nan', 'none', ''] or 
                        param_name.lower() in ['nan', 'none', ''] or
                        not class_name or not param_name or
                        class_name == 'nan' or param_name == 'nan'):
                        continue
                        
                    if "bts" in mod_status:
                        color = "red"
                    elif "on-line" in mod_status:
                        color = "green"
                    elif "not modifiable" in mod_status:
                        color = "gray"
                    else:
                        color = "gray"
                        
                    mand = "(M)" if "mandatory" in required else "(O)" if "optional" in required else ""
                    
                    uml_data[class_name]["attributes"].append({
                        "name": param_name,
                        "type": data_type,
                        "mandatory": mand,
                        "color": color,
                        "parent": parent
                    })
                    
                    if "/" in class_name:
                        parts = class_name.split("/")
                        for i in range(1, len(parts)):
                            parent_class = "/".join(parts[:i])
                            child_class = "/".join(parts[:i+1])
                            uml_data[parent_class]["relationships"].add(child_class)
                            
                    all_classes.add(class_name)
        
        return sorted(all_classes)
    except Exception as e:
        print(f"Error loading UML data: {e}")
        return []

@app.route('/parameter.html')
def parameter_page():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        return redirect(url_for('landing_page'))
    return render_template('parameter.html')

@app.route('/get-parameters')
def get_parameters():
    try:
        if not parameters_list:
            return jsonify({
                "error": "No parameters loaded. Upload an Excel file first.",
                "parameters": []
            }), 500
        return jsonify({"parameters": parameters_list})
    except Exception as e:
        return jsonify({"error": str(e), "parameters": []}), 500

@app.route('/get-relation', methods=['POST'])
def get_relation():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        param = data.get("parameter")
        if not param:
            return jsonify({"error": "No parameter specified"}), 400
        
        relation = parameter_relations.get(param)
        
        if not relation:
            for key, value in parameter_relations.items():
                if key.lower() == param.lower():
                    relation = value
                    break
                    
        if not relation:
            relation = "No relation found for this parameter."
            
        return jsonify({"parameter": param, "relation": relation})
    except Exception as e:
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/reload-data', methods=['POST'])
def reload_data():
    try:
        file_paths = session.get('uploaded_files', [])
        if not file_paths:
            return jsonify({"success": False, "error": "No files uploaded"}), 400
        
        load_excel_data(file_paths[0])
        return jsonify({
            "success": True,
            "message": f"Data reloaded. Found {len(parameters_list)} parameters."
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/test-data')
def test_data():
    file_paths = session.get('uploaded_files', [])
    return jsonify({
        "parameters_count": len(parameters_list),
        "relations_count": len(parameter_relations),
        "sample_parameters": parameters_list[:5] if parameters_list else [],
        "uploaded_files": file_paths
    })

# --------- UML Diagram Generator ---------
@app.route('/umldiagram.html')
def uml_ui():
    if 'uploaded_files' not in session or not session['uploaded_files']:
        return redirect(url_for('landing_page'))
    return render_template('umldiagram.html')

@app.route('/upload-main', methods=['POST'])
def upload_main():
    """Handle file upload from main page and store in session"""
    try:
        uploaded_files = request.files.getlist("excel_files")
        diagram_type = request.form.get('diagram_type', 'uml')
        available_files = request.form.getlist('available_files')
        
        if not uploaded_files and not available_files:
            return jsonify({"success": False, "error": "No files selected"}), 400

        session_id = session.get('session_id')
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
        session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
        os.makedirs(session_dir, exist_ok=True)
        file_paths = []

        # Process newly uploaded files
        for file in uploaded_files:
            if file and file.filename.endswith(('.xlsx', '.xls', '.xlsm')):
                filename = secure_filename(file.filename)
                file_path = os.path.join(session_dir, filename)
                file.save(file_path)
                file_paths.append(file_path)
                # Copy to global uploads folder for listing
                global_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                shutil.copy2(file_path, global_path)

        # Process selected available files (copy to session)
        for filename in available_files:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')):
                safe_filename = secure_filename(filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                if os.path.exists(source_path):
                    dest_path = os.path.join(session_dir, safe_filename)
                    shutil.copy2(source_path, dest_path)
                    file_paths.append(dest_path)

        if not file_paths:
            return jsonify({"success": False, "error": "No valid Excel files found"}), 400

        session['uploaded_files'] = file_paths
        session['diagram_type'] = diagram_type

        # Load data based on diagram type using the corrected logic
        if diagram_type == 'uml':
            classes = load_uml_data(file_paths)
            load_excel_data(file_paths[0])  # Also load parameter data
            return jsonify({"success": True, "redirect": url_for('uml_ui')})
        else:
            load_excel_data(file_paths[0])
            return jsonify({"success": True, "redirect": url_for('parameter_page')})
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/select-available-files', methods=['POST'])
def select_available_files():
    """Handle selection of available files without upload"""
    try:
        data = request.get_json()
        selected_filenames = data.get('filenames', [])
        diagram_type = data.get('diagram_type', 'uml')

        if not selected_filenames:
            return jsonify({"success": False, "error": "No files selected"}), 400

        session_id = session.get('session_id')
        if not session_id:
            import uuid
            session_id = str(uuid.uuid4())
            session['session_id'] = session_id
            
        session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
        os.makedirs(session_dir, exist_ok=True)
        file_paths = []

        # Copy selected files to session directory
        for filename in selected_filenames:
            if filename and filename.endswith(('.xlsx', '.xls', '.xlsm')):
                safe_filename = secure_filename(filename)
                source_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
                if os.path.exists(source_path):
                    dest_path = os.path.join(session_dir, safe_filename)
                    shutil.copy2(source_path, dest_path)
                    file_paths.append(dest_path)

        if not file_paths:
            return jsonify({"success": False, "error": "No valid files found"}), 400

        session['uploaded_files'] = file_paths
        session['diagram_type'] = diagram_type

        # Load data based on diagram type using corrected logic
        if diagram_type == 'uml':
            classes = load_uml_data(file_paths)
            load_excel_data(file_paths[0])  # Also load parameter data
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(classes)} classes.",
                "redirect": "/umldiagram.html"
            })
        else:
            load_excel_data(file_paths[0])
            return jsonify({
                "success": True,
                "message": f"Files loaded successfully. Found {len(parameters_list)} parameters.",
                "redirect": "/parameter.html"
            })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle UML diagram generation using session files"""
    global uml_data
    
    file_paths = session.get('uploaded_files', [])
    if not file_paths:
        return jsonify({
            "success": False,
            "error": "No files found in session. Please upload files from the main page."
        }), 400
    
    # If UML data not already loaded, load it
    if not uml_data:
        classes = load_uml_data(file_paths)
        # Add "All Classes" option at the beginning
        classes_with_all = ["All Classes"] + classes
        return jsonify({
            "success": True,
            "classes": classes_with_all
        })
    else:
        all_classes = sorted(uml_data.keys())
        # Add "All Classes" option at the beginning
        classes_with_all = ["All Classes"] + all_classes
        return jsonify({
            "success": True,
            "classes": classes_with_all
        })

@app.route('/uml', methods=['POST'])
def generate_uml():
    data = request.get_json()
    selected_class = data.get("parameter")
    depth = int(data.get("depth", 1))
    
    if not selected_class:
        return jsonify({"uml": "graph TD\n%% No class selected"})

    # Handle "All Classes" selection
    if selected_class == "All Classes":
        return generate_all_classes_uml()
    
    if selected_class not in uml_data:
        return jsonify({"uml": "graph TD\n%% Invalid class selected"})

    visited = set()
    result_classes = {}
    queue = deque()
    queue.append((selected_class, 0))

    while queue:
        current_cls, current_depth = queue.popleft()
        if current_cls in visited or current_depth > depth:
            continue

        visited.add(current_cls)
        result_classes[current_cls] = uml_data[current_cls]

        if current_depth < depth:
            for rel in uml_data[current_cls]["relationships"]:
                queue.append((rel, current_depth + 1))

    lines = ["graph TD"]

    for cls, info in result_classes.items():
        safe_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        label_lines = [f"<b>{cls}</b>"]
        for attr in info["attributes"]:
            label = f"<span style='color:{attr['color']}'>+ {attr['name']} : {attr['type']} {attr['mandatory']}</span>"
            label_lines.append(label)
        html_label = "<br>".join(label_lines).replace('"', '&quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    for cls, info in result_classes.items():
        from_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        for rel in info["relationships"]:
            if rel in result_classes:
                to_cls = rel.replace("/", "_").replace("-", "_").replace(".", "_")
                lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines)})

def generate_all_classes_uml():
    """Generate UML diagram for all classes"""
    if not uml_data:
        return jsonify({"uml": "graph TD\n%% No classes available"})

    lines = ["graph TD"]

    # Add all classes with their attributes
    for cls, info in uml_data.items():
        safe_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        label_lines = [f"<b>{cls}</b>"]
        
        # Limit attributes to prevent diagram from being too crowded
        # You can adjust this number or remove the limit entirely
        max_attrs = 5  # Show only first 5 attributes per class
        attrs_to_show = info["attributes"][:max_attrs]
        
        for attr in attrs_to_show:
            label = f"<span style='color:{attr['color']}'>+ {attr['name']} : {attr['type']} {attr['mandatory']}</span>"
            label_lines.append(label)
            
        if len(info["attributes"]) > max_attrs:
            label_lines.append(f"<i>... and {len(info['attributes']) - max_attrs} more</i>")
            
        html_label = "<br>".join(label_lines).replace('"', '&quot;')
        lines.append(f'{safe_cls}["{html_label}"]')

    # Add all relationships
    for cls, info in uml_data.items():
        from_cls = cls.replace("/", "_").replace("-", "_").replace(".", "_")
        for rel in info["relationships"]:
            if rel in uml_data:  # Only add relationship if target class exists
                to_cls = rel.replace("/", "_").replace("-", "_").replace(".", "_")
                lines.append(f"{from_cls} --> {to_cls}")

    return jsonify({"uml": "\n".join(lines)})

@app.route('/clear-session', methods=['POST'])
def clear_session():
    try:
        session_id = session.get('session_id')
        if session_id:
            session_dir = os.path.join(app.config['TEMP_FOLDER'], session_id)
            if os.path.exists(session_dir):
                shutil.rmtree(session_dir)
                
        session.clear()
        global parameters_list, parameter_relations, uml_data
        parameters_list = []
        parameter_relations = {}
        uml_data.clear()
        return jsonify({"success": True, "message": "Session cleared"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --------- Main Entry ---------
@app.route('/')
def landing_page():
    return render_template('main.html')

@app.route('/get-available-files')
def get_available_files():
    try:
        files = []
        upload_folder = app.config['UPLOAD_FOLDER']
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder, exist_ok=True)
            
        for filename in os.listdir(upload_folder):
            file_path = os.path.join(upload_folder, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.xls', '.xlsx', '.xlsm')):
                files.append({
                    "name": filename,
                    "size": os.path.getsize(file_path)
                })
        return jsonify({"success": True, "files": files})
    except Exception as e:
        print(f"Error getting available files: {e}")
        return jsonify({"success": False, "files": [], "error": str(e)})

if __name__ == '__main__':
    app.run(debug=True)