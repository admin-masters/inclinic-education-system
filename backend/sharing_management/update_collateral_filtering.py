import re

def update_views_file():
    # Path to the views.py file
    views_path = r'c:\Users\bhart\OneDrive\inclinic-education-system\backend\sharing_management\views.py'
    
    # Path to our updated function
    updated_function_path = r'c:\Users\bhart\OneDrive\inclinic-education-system\backend\sharing_management\prefilled_fieldrep_gmail_share_collateral_updated.py'
    
    try:
        # Read the original views.py content
        with open(views_path, 'r', encoding='utf-8') as f:
            views_content = f.read()
        
        # Read the updated function content
        with open(updated_function_path, 'r', encoding='utf-8') as f:
            updated_function = f.read()
        
        # Use regex to find and replace the function
        # This pattern looks for the function definition and everything until the next function definition
        pattern = r'def prefilled_fieldrep_gmail_share_collateral\(request\):.*?(?=def \w+\()'
        
        # Replace the function with the updated version
        updated_views_content, num_replacements = re.subn(
            pattern, 
            updated_function, 
            views_content, 
            flags=re.DOTALL
        )
        
        if num_replacements == 0:
            print("Warning: No function was replaced. The function signature might have changed.")
        else:
            # Create a backup of the original file
            with open(views_path + '.bak', 'w', encoding='utf-8') as f:
                f.write(views_content)
            
            # Write the updated content back to views.py
            with open(views_path, 'w', encoding='utf-8') as f:
                f.write(updated_views_content)
            
            print("Successfully updated the prefilled_fieldrep_gmail_share_collateral function.")
            print("A backup of the original file has been saved as views.py.bak")
    
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Please make sure the files exist and you have the necessary permissions.")

if __name__ == "__main__":
    update_views_file()
