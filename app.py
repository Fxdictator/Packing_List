import os
import json
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, send_file
from datetime import datetime
import io

app = Flask(__name__)

# --- Configuration & Helper Functions ---
DATA_FILE = 'packing_data.json'

# NEW: Define box types and their dimensions (L, W, H in cm)
BOX_TYPES = {
    "Type 1 (Square)": {"L": 52, "W": 52, "H": 40},
    "Type 2 (Tall Large)": {"L": 44, "W": 44, "H": 60},
    "Type 3 (Rectangle)": {"L": 52, "W": 30, "H": 30}
}

def calculate_volumetric_weight(dims):
    """Calculates volumetric weight using the (L*W*H)/5000 formula."""
    return (dims["L"] * dims["W"] * dims["H"]) / 5000

def load_data():
    """Loads packing data from the JSON file."""
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_data(data):
    """Saves packing data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- Routes ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main page to display and create boxes."""
    data = load_data()
    if request.method == 'POST':
        box_name = request.form['box_name'].strip()
        box_type = request.form['box_type']
        if box_name and box_name not in data:
            data[box_name] = {"type": box_type, "items": []}
            save_data(data)
        return redirect(url_for('index'))
    
    sorted_box_names = sorted(data.keys(), key=lambda x: int(''.join(filter(str.isdigit, x))) if any(char.isdigit() for char in x) else float('inf'))
    
    boxes_with_details = []
    for box_name in sorted_box_names:
        box_info = data[box_name]
        
        # --- THIS IS THE FIX ---
        # Check if the data is in the old format (a list) or new format (a dict)
        if isinstance(box_info, dict):
            # New format: It's a dictionary, so we can get the type
            box_type = box_info.get("type", "N/A")
            item_count = len(box_info.get("items", []))
            volumetric_weight = 0
            if box_type in BOX_TYPES:
                dims = BOX_TYPES[box_type]
                volumetric_weight = calculate_volumetric_weight(dims)
            weight_str = f"{volumetric_weight:.2f} kg"
        else:
            # Old format: It's just a list of items
            box_type = "N/A (Legacy)"
            item_count = len(box_info)
            weight_str = "N/A"
        # --- END OF FIX ---

        boxes_with_details.append({
            'name': box_name, 
            'count': item_count,
            'type': box_type,
            'weight': weight_str
        })
    
    return render_template('index.html', boxes=boxes_with_details, box_types=BOX_TYPES.keys())


# The rest of your app.py file remains the same...

@app.route('/box/<box_name>', methods=['GET', 'POST'])
def view_box(box_name):
    """Page to view and add items to a specific box."""
    data = load_data()
    if box_name not in data:
        return redirect(url_for('index'))

    # Gracefully handle both old and new data formats
    box_items_list = data[box_name]
    if isinstance(box_items_list, dict):
        box_items_list = box_items_list.get('items', [])

    if request.method == 'POST':
        item = request.form['item']
        description = request.form['description']
        qty = int(request.form['quantity'])
        
        if item and description and qty > 0:
            new_item = {'item': item, 'description': description, 'quantity': qty}
            # If it's old format, we can't add, but we prevent a crash
            # A better solution would be to auto-convert, but this is safer
            if isinstance(data[box_name], dict):
                 data[box_name]['items'].append(new_item)
                 save_data(data)
        return redirect(url_for('view_box', box_name=box_name))

    return render_template('box_view.html', box_name=box_name, items=box_items_list)


@app.route('/edit/<box_name>/<int:item_index>', methods=['GET', 'POST'])
def edit_item(box_name, item_index):
    data = load_data()
    
    box_content = data.get(box_name)
    if not box_content:
        return redirect(url_for('index'))

    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])
    
    if not 0 <= item_index < len(items_list):
        return redirect(url_for('view_box', box_name=box_name))
        
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
    if not box_content:
        return redirect(url_for('index'))

    items_list = box_content if isinstance(box_content, list) else box_content.get('items', [])

    if 0 <= item_index < len(items_list):
        del items_list[item_index]
        save_data(data)
    return redirect(url_for('view_box', box_name=box_name))


@app.route('/delete_box/<box_name>')
def delete_box(box_name):
    """Deletes an entire box."""
    data = load_data()
    if box_name in data:
        del data[box_name]
        save_data(data)
    return redirect(url_for('index'))

@app.route('/export/<box_name>')
def export_box(box_name):
    """Exports a box's inventory to an Excel file."""
    data = load_data()
    box_info = data.get(box_name)
    
    if not box_info:
        return redirect(url_for('index'))

    items = []
    volumetric_weight_str = "N/A"
    
    if isinstance(box_info, dict):
        items = box_info.get('items', [])
        box_type = box_info.get("type", "N/A")
        if box_type in BOX_TYPES:
            dims = BOX_TYPES[box_type]
            weight = calculate_volumetric_weight(dims)
            volumetric_weight_str = f"{weight:.2f} kg"
    else:
        # Handle legacy list format
        items = box_info

    df = pd.DataFrame(items) if items else pd.DataFrame(columns=['item', 'description', 'quantity'])
    
    df = df[['item', 'description', 'quantity']] 
    df.columns = ['ITEM', 'DESCRIPTION', 'SHIPPED QTY'] 

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        ws = writer.book.create_sheet(title="PACKING SLIP")
        
        ws.merge_cells('D1:F1'); ws['D1'] = 'PACKING SLIP'
        ws['F2'] = 'DATE'; ws['G2'] = datetime.now().strftime('%d/%m/%Y')
        ws['B4'] = 'SHIPPED FROM:'; ws['D4'] = 'SHIP TO:'
        ws['B5'] = 'Jolin Tamora'; ws['D5'] = 'Jolin Tamora'
        ws['B6'] = 'Apartment 802, Satin House'; ws['D6'] = 'Jl. Pantai Batu Bolong,'
        ws['B7'] = '15 Piazza Walk'; ws['D7'] = 'Gg. Bantan No.11C'
        ws['B8'] = 'London'; ws['D8'] = 'Badung, Bali'
        ws['B9'] = 'United Kingdom'; ws['D9'] = 'Kuta Utara'
        ws['B10'] = 'E1 8PW'; ws['D10'] = '80361'

        start_row = 12 
        df.to_excel(writer, sheet_name='PACKING SLIP', startrow=start_row, index=False)
        
        total_qty = df['SHIPPED QTY'].sum()
        total_row = start_row + len(df) + 2
        ws[f'F{total_row}'] = 'TOTAL:'; ws[f'G{total_row}'] = total_qty
        ws[f'F{total_row+1}'] = 'Volumetric Weight:'; ws[f'G{total_row+1}'] = volumetric_weight_str

        if 'Sheet1' in writer.book.sheetnames:
            writer.book.remove(writer.book['Sheet1'])

    output.seek(0)
    
    return send_file(
        output,
        as_attachment=True,
        download_name=f'{box_name}_Packing_List.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)