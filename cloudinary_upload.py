import cloudinary
import cloudinary.uploader
import cloudinary.api
import os
from werkzeug.utils import secure_filename
import secrets
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configure Cloudinary from environment variables
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

def upload_member_document(file, member_id, document_type):
    """
    Upload member document to Cloudinary
    Returns: dictionary with upload details or None if failed
    """
    try:
        if not file or file.filename == '':
            return None
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{document_type}_{member_id}_{timestamp}_{secrets.token_hex(4)}.{file_extension}"
        
        # Determine folder based on document type
        folder_mapping = {
            'id_front': 'members/id_cards/front',
            'id_back': 'members/id_cards/back',
            'profile_photo': 'members/profile_photos',
            'signature': 'members/signatures',
            'other': 'members/documents'
        }
        
        folder = folder_mapping.get(document_type, 'members/documents')
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            file,
            public_id=f"{folder}/{unique_filename}",
            folder=folder,
            overwrite=True,
            resource_type="auto",  # Auto-detect resource type
            transformation=get_upload_transformation(document_type),
            tags=[f"member_{member_id}", document_type, "lunserk_sacco"]
        )
        
        # Extract relevant data
        upload_data = {
            'public_id': result['public_id'],
            'secure_url': result['secure_url'],
            'url': result['url'],
            'format': result['format'],
            'width': result.get('width'),
            'height': result.get('height'),
            'bytes': result.get('bytes'),
            'original_filename': original_filename,
            'document_type': document_type
        }
        
        print(f"✅ Document uploaded to Cloudinary: {upload_data['secure_url']}")
        return upload_data
        
    except Exception as e:
        print(f"❌ Cloudinary upload error: {e}")
        return None

def get_upload_transformation(document_type):
    """
    Get appropriate transformations for different document types
    """
    transformations = {
        'profile_photo': [
            {'width': 400, 'height': 400, 'crop': 'fill', 'gravity': 'face'},
            {'quality': 'auto:good'},
            {'format': 'webp'}
        ],
        'id_front': [
            {'width': 800, 'height': 600, 'crop': 'limit'},
            {'quality': 'auto:best'},
            {'format': 'jpg'}
        ],
        'id_back': [
            {'width': 800, 'height': 600, 'crop': 'limit'},
            {'quality': 'auto:best'},
            {'format': 'jpg'}
        ],
        'signature': [
            {'width': 300, 'height': 150, 'crop': 'fit'},
            {'quality': 'auto'},
            {'format': 'png', 'background': 'transparent'}
        ]
    }
    
    return transformations.get(document_type, [
        {'width': 800, 'height': 800, 'crop': 'limit'},
        {'quality': 'auto'},
        {'format': 'jpg'}
    ])

def delete_cloudinary_file(public_id):
    """
    Delete file from Cloudinary
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        if result.get('result') == 'ok':
            print(f"✅ File deleted from Cloudinary: {public_id}")
            return True
        else:
            print(f"❌ Failed to delete file: {result}")
            return False
    except Exception as e:
        print(f"❌ Cloudinary delete error: {e}")
        return False

def get_cloudinary_url(public_id, transformation=None):
    """
    Generate Cloudinary URL with optional transformations
    """
    try:
        if transformation:
            return cloudinary.utils.cloudinary_url(public_id, **transformation)[0]
        else:
            return cloudinary.utils.cloudinary_url(public_id)[0]
    except Exception as e:
        print(f"❌ Error generating Cloudinary URL: {e}")
        return None

def validate_image_file(file):
    """
    Validate uploaded image file
    """
    if not file:
        return False, "No file uploaded"
    
    # Check file extension
    allowed_extensions = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff'}
    filename = secure_filename(file.filename)
    
    if '.' not in filename:
        return False, "No file extension"
    
    extension = filename.rsplit('.', 1)[1].lower()
    if extension not in allowed_extensions:
        return False, f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
    
    # Check file size (max 5MB)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Reset to beginning
    
    max_size = 5 * 1024 * 1024  # 5MB
    if file_size > max_size:
        return False, f"File too large. Maximum size: 5MB"
    
    return True, "File is valid"

# Test function
def test_cloudinary_connection():
    """
    Test Cloudinary connection and configuration
    """
    try:
        # Try to get account info
        account_info = cloudinary.api.ping()
        print("✅ Cloudinary connection successful")
        print(f"   Status: {account_info.get('status')}")
        
        # Test with a simple upload (optional)
        # print("Testing upload with sample data...")
        # test_result = upload_member_document(open('test.jpg', 'rb'), 'test_123', 'profile_photo')
        # if test_result:
        #     print(f"✅ Test upload successful: {test_result['secure_url']}")
        #     # Clean up test file
        #     delete_cloudinary_file(test_result['public_id'])
        #     print("✅ Test file cleaned up")
        
        return True
    except Exception as e:
        print(f"❌ Cloudinary connection failed: {e}")
        print("   Please check your Cloudinary credentials in .env file")
        return False

if __name__ == "__main__":
    print("Testing Cloudinary configuration...")
    test_cloudinary_connection()