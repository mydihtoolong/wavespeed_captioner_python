import os

def prepend_trigger():
    # Define the subdirectory target
    target_dir = os.path.join('.', 'lora-db')
    
    # 1. Check if the lora-db directory actually exists
    if not os.path.exists(target_dir):
        print(f"Error: The subdirectory '{target_dir}' was not found.")
        print("Please make sure this script is running in the same folder as lora_tool.py")
        return

    # 2. Ask the user for the trigger word with your custom example
    print("\n--- LoRA Trigger Word Prepender ---")
    print("For example 'PersonChar123' or any other word that Zimage doesn't know about yet.")
    user_input = input("Enter your trigger word: ").strip()
    
    if not user_input:
        print("Operation cancelled. No trigger word was provided.")
        return

    # 3. Automatically format with a comma and space at the end
    formatted_trigger = f"{user_input}, "

    # 4. Gather all .txt files in the subdirectory
    txt_files = [f for f in os.listdir(target_dir) if f.endswith('.txt')]
    
    if not txt_files:
        print(f"No .txt files found inside the '{target_dir}' directory.")
        return

    print(f"\nFound {len(txt_files)} text files. Prepending '{formatted_trigger}' to all captions...")
    
    success_count = 0
    
    # 5. Loop through and update each file
    for filename in txt_files:
        file_path = os.path.join(target_dir, filename)
        
        # Read the existing caption
        with open(file_path, mode='r', encoding='utf-8') as f:
            existing_content = f.read()
        
        # Merge them (e.g., "PersonChar123, An image of a cat...")
        new_content = formatted_trigger + existing_content
        
        # Overwrite the file with the new combined string
        with open(file_path, mode='w', encoding='utf-8') as f:
            f.write(new_content)
            
        success_count += 1

    print(f"Done! Successfully updated {success_count} files inside '{target_dir}'.")

if __name__ == "__main__":
    prepend_trigger()
