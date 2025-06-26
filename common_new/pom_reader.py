import xml.etree.ElementTree as ET
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

def get_pom_version() -> str:
    """
    Reads the version from pom.xml in the project root.
    It looks for the version exclusively within the <parent> tag.
    """
    try:
        # This script is in common_new, and pom.xml is in the project root.
        pom_path = Path(__file__).parent.parent / 'pom.xml'
        
        if not pom_path.is_file():
            logger.warning("pom.xml not found at %s", pom_path)
            return "pom.xml not found"

        tree = ET.parse(pom_path)
        root = tree.getroot()

        # Extract namespace if present
        namespace = ''
        if '}' in root.tag:
            namespace = root.tag.split('}')[0][1:]
        
        ns_map = {'mvn': namespace} if namespace else {}
        
        # Search for version in parent tag
        # XPath for parent > version
        path_parent_version = './mvn:parent/mvn:version' if namespace else './parent/version'
        version_element = root.find(path_parent_version, ns_map)
        
        if version_element is not None and version_element.text:
            return version_element.text.strip()

        logger.warning("Version not found within <parent> tag in pom.xml")
        return "unknown version"

    except ET.ParseError as e:
        logger.error("Error parsing pom.xml: %s", e)
        return "Error parsing pom.xml"
    except Exception as e:
        logger.error("An unexpected error occurred while reading pom.xml: %s", e, exc_info=True)
        return "An unexpected error occurred while reading pom.xml" 