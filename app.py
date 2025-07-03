import os
import json
from flask import Flask, render_template, request, redirect, url_for, send_file, Response
from datetime import datetime
import io
from weasyprint import HTML
from math import ceil # Import the ceil function directly

app = Flask(__name__)

# --- Configuration & Helper Functions ---
DATA_FILE = 'packing_data.json'
CONFIG_FILE = 'config.json'

BOX_TYPES = {
    "Type 1 (Square)": {"L": 52, "W": 52, "H": 40},
    "Type 2 (Tall Large)": {"L": 44, "W": 44, "H": 60},
    "Type 3 (Rectangle)": {"L": 52, "W": 30, "H": 30}
}

def load_config():
    """Loads configuration from JSON file."""
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        # Fallback to default addresses if config file is missing
        # This is just a safety net, ideally the app should ensure config.json exists
        print(f"Warning: {CONFIG_FILE} not found. Using default addresses.")
        config = {
            "FROM_ADDRESS": {
                "name": "Default From Name", "line1": "Default From Line 1", "line2": "",
                "city": "Default City", "country": "Default Country", "postcode": "00000"
            },
            "TO_ADDRESS": {
                "name": "Default To Name", "line1": "Default To Line 1", "line2": "",
                "city_province": "Default Province", "area": "Default Area", "postcode": "00000"
            }
        }
    except json.JSONDecodeError:
        print(f"Error: Could not decode {CONFIG_FILE}. Using default addresses.")
        # Similar fallback for corrupted JSON
        config = {
            "FROM_ADDRESS": {"name": "Error From"}, "TO_ADDRESS": {"name": "Error To"} # Simplified error defaults
        }
    return config.get("FROM_ADDRESS", {}), config.get("TO_ADDRESS", {})

FROM_ADDRESS, TO_ADDRESS = load_config()

def calculate_volumetric_weight(dims):
    """Calculates volumetric weight and ALWAYS rounds up."""
    return ceil((dims["L"] * dims["W"] * dims["H"]) / 5000)

def load_data():
    if not os.path.exists(DATA_FILE): return {}
    with open(DATA_FILE, 'r') as f:
        try: return json.load(f)
        except json.JSONDecodeError: return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f: json.dump(data, f, indent=4)

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    data = load_data()
    if request.method == 'POST':
        box_name = request.form['box_name'].strip()
        box_type = request.form['box_type']
        # Get actual weight from form, default to 0 if empty
        actual_weight = request.form.get('actual_weight', 0)
        
        if box_name and box_name not in data:
            data[box_name] = {
                "type": box_type, 
                "items": [],
                "actual_weight": float(actual_weight) if actual_weight else 0
            }
            save_data(data)
        return redirect(url_for('index'))
    
    sorted_box_names = sorted(data.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else float('inf'))
    
    boxes_with_details = []
    total_items_all_boxes = 0
    total_volumetric_weight_all_boxes = 0
    total_actual_weight_all_boxes = 0

    for box_name in sorted_box_names:
        box_info = data[box_name]
        item_count = 0
        actual_weight_val = 0
        volumetric_weight_val = 0
        
        if isinstance(box_info, dict):
            box_type = box_info.get("type", "N/A")
            items_list = box_info.get("items", [])
            item_count = sum(item.get('quantity', 0) for item in items_list) # Sum of quantities
            actual_weight_val = box_info.get("actual_weight", 0)
            if box_type in BOX_TYPES:
                dims = BOX_TYPES[box_type]
                volumetric_weight_val = calculate_volumetric_weight(dims)
            volumetric_weight_str = f"{volumetric_weight_val} kg"
        else: # Legacy format
            box_type = "N/A (Legacy)"
            # Assuming legacy items might not have quantity, count them as 1 each or adjust if structure is known
            item_count = len(box_info) if isinstance(box_info, list) else 0
            volumetric_weight_str = "N/A"
            # actual_weight_val remains 0 for legacy as it wasn't stored then

        boxes_with_details.append({
            'name': box_name, 
            'count': item_count, # This is now total quantity of items in the box
            'type': box_type, 
            'volumetric_weight': volumetric_weight_str,
            'actual_weight': f"{actual_weight_val} kg"
        })

        total_items_all_boxes += item_count
        total_volumetric_weight_all_boxes += volumetric_weight_val
        total_actual_weight_all_boxes += actual_weight_val
    
    return render_template('index.html',
                           boxes=boxes_with_details,
                           box_types=BOX_TYPES.keys(),
                           total_items=total_items_all_boxes,
                           total_volumetric_weight=f"{total_volumetric_weight_all_boxes} kg",
                           total_actual_weight=f"{total_actual_weight_all_boxes:.1f} kg") # Format actual weight

@app.route('/edit_box_weight/<box_name>', methods=['GET', 'POST'])
def edit_box_weight(box_name):
    data = load_data()
    if box_name not in data or not isinstance(data[box_name], dict):
        return redirect(url_for('index')) # Or show an error

    box_info = data[box_name]

    if request.method == 'POST':
        new_actual_weight = request.form.get('actual_weight')
        if new_actual_weight is not None:
            try:
                box_info['actual_weight'] = float(new_actual_weight)
                save_data(data)
                return redirect(url_for('index'))
            except ValueError:
                # Handle error if conversion to float fails, e.g., flash a message
                pass
        return redirect(url_for('edit_box_weight', box_name=box_name)) # Redirect back if no weight or error

    current_weight = box_info.get('actual_weight', 0)
    return render_template('edit_box_weight.html', box_name=box_name, current_weight_kg=current_weight)

# ... (view_box, edit_item, delete_item, delete_box routes remain mostly the same) ...
@app.route('/box/<box_name>', methods=['GET', 'POST'])
def view_box(box_name):
    data = load_data()
    if box_name not in data: return redirect(url_for('index'))
    box_content = data[box_name]
    box_items_list = box_content.get('items', []) if isinstance(box_content, dict) else box_content
    if request.method == 'POST':
        if isinstance(box_content, dict):
            new_item = {'item': request.form['item'], 'description': request.form['description'], 'quantity': int(request.form['quantity'])}
            box_content['items'].append(new_item)
            save_data(data)
        return redirect(url_for('view_box', box_name=box_name))
    return render_template('box_view.html', box_name=box_name, items=box_items_list)

@app.route('/edit/<box_name>/<int:item_index>', methods=['GET', 'POST'])
def edit_item(box_name, item_index):
    data = load_data()
    box_content = data.get(box_name)
    if not box_content: return redirect(url_for('index'))
    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])
    if not 0 <= item_index < len(items_list): return redirect(url_for('view_box', box_name=box_name))
    item_to_edit = items_list[item_index]
    if request.method == 'POST':
        item_to_edit['item'] = request.form['item']
        item_to_edit['description'] = request.form['description']
        item_to_edit['quantity'] = int(request.form['quantity'])
        save_data(data)
        return redirect(url_for('view_box', box_name=box_name))
    return render_template('edit_item.html', box_name=box_name, item_index=item_index, item=item_to_edit)

@app.route('/delete/<box_name>/<int:item_index>')
def delete_item(box_name, item_index):
    data = load_data()
    box_content = data.get(box_name)
    if not box_content: return redirect(url_for('index'))
    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])
    if 0 <= item_index < len(items_list):
        del items_list[item_index]
        save_data(data)
    return redirect(url_for('view_box', box_name=box_name))

@app.route('/delete_box/<box_name>')
def delete_box(box_name):
    data = load_data()
    if box_name in data:
        del data[box_name]
        save_data(data)
    return redirect(url_for('index'))

def get_export_data(box_name):
    """Helper function to gather data for PDF and Print views."""
    data = load_data()
    box_info = data.get(box_name)
    if not box_info:
        return None

    items, vol_wt, act_wt, total_qty = [], 0, 0, 0
    
    if isinstance(box_info, dict):
        items = box_info.get('items', [])
        box_type = box_info.get("type", "N/A")
        act_wt = box_info.get("actual_weight", 0)
        total_qty = sum(item['quantity'] for item in items)
        if box_type in BOX_TYPES:
            vol_wt = calculate_volumetric_weight(BOX_TYPES[box_type])
    else:
        items = box_info
        total_qty = sum(item['quantity'] for item in items)

    return {
        "items": items,
        "total_qty": total_qty,
        "volumetric_weight_str": f"{vol_wt} kg",
        "actual_weight_str": f"{act_wt} kg"
    }

@app.route('/export_pdf/<box_name>')
def export_pdf(box_name):
    export_data = get_export_data(box_name)
    if not export_data: return redirect(url_for('index'))
    
    rendered_html = render_template('pdf_template.html', box_name=box_name, current_date=datetime.now().strftime('%d/%m/%Y'), from_address=FROM_ADDRESS, to_address=TO_ADDRESS, **export_data)
    pdf = HTML(string=rendered_html).write_pdf()
    return Response(pdf, mimetype='application/pdf', headers={'Content-Disposition': f'attachment;filename={box_name}_Packing_List.pdf'})

@app.route('/print/<box_name>')
def print_packing_slip(box_name):
    export_data = get_export_data(box_name)
    if not export_data: return redirect(url_for('index'))
    
    return render_template('print_template.html', box_name=box_name, current_date=datetime.now().strftime('%d/%m/%Y'), from_address=FROM_ADDRESS, to_address=TO_ADDRESS, **export_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)