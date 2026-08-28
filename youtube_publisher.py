"""
Direct YouTube OAuth & Publishing Module for OpenShorts.
Allows 1-click Google/YouTube OAuth authentication and direct publishing of generated Shorts
using the official Google YouTube Data API v3.
"""

import os
import json
import logging
from typing import Optional, Dict, Any, Tuple
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger("YouTubePublisher")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "youtube_credentials.json")
CLIENT_SECRETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "client_secrets.json")


class YouTubePublisher:
    def __init__(self, credentials_path: str = CREDENTIALS_FILE):
        self.credentials_path = credentials_path
        os.makedirs(os.path.dirname(self.credentials_path), exist_ok=True)

    def is_authenticated(self) -> bool:
        creds = self.get_credentials()
        return creds is not None and creds.valid

    def get_credentials(self) -> Optional[Credentials]:
        if os.path.exists(self.credentials_path):
            try:
                with open(self.credentials_path, "r") as f:
                    data = json.load(f)
                creds = Credentials.from_authorized_user_info(data, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    import google.auth.transport.requests
                    creds.refresh(google.auth.transport.requests.Request())
                    self.save_credentials(creds)
                return creds
            except Exception as e:
                logger.error(f"Error loading YouTube credentials: {e}")
        return None

    def save_credentials(self, credentials: Credentials):
        with open(self.credentials_path, "w") as f:
            f.write(credentials.to_json())

    def get_auth_url(self, client_id: str, client_secret: str, redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob") -> Tuple[str, Any]:
        """Generates Google OAuth consent URL for 1-click authentication."""
        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [redirect_uri]
            }
        }
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        flow.redirect_uri = redirect_uri
        auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
        return auth_url, flow

    def exchange_code_for_token(self, flow: Any, code: str) -> bool:
        """Exchanges the authorization code for an OAuth access token."""
        try:
            flow.fetch_token(code=code.strip())
            self.save_credentials(flow.credentials)
            return True
        except Exception as e:
            logger.error(f"Error exchanging code: {e}")
            return False

    def save_credentials_from_json(self, json_str: str) -> bool:
        """Saves credentials directly from a JSON blob."""
        try:
            data = json.loads(json_str)
            creds = Credentials.from_authorized_user_info(data, SCOPES)
            self.save_credentials(creds)
            return True
        except Exception as e:
            logger.error(f"Error parsing credentials JSON: {e}")
            return False

    def get_channel_info(self) -> Optional[Dict[str, str]]:
        """Retrieves authenticated channel title & thumbnail."""
        creds = self.get_credentials()
        if not creds:
            return None
        try:
            youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)
            request = youtube.channels().list(part="snippet", mine=True)
            response = request.execute()
            items = response.get("items", [])
            if items:
                snippet = items[0]["snippet"]
                return {
                    "title": snippet.get("title", "Canal do YouTube"),
                    "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", "")
                }
        except Exception as e:
            logger.error(f"Error fetching channel info: {e}")
        return None

    def upload_short(self, video_path: str, title: str, description: str, tags: Optional[list] = None, privacy_status: str = "public") -> Dict[str, Any]:
        """Uploads video as a YouTube Short using YouTube Data API v3."""
        creds = self.get_credentials()
        if not creds:
            raise ValueError("Conta do YouTube não autenticada. Faça login na aba de Publicação.")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Arquivo de vídeo não encontrado: {video_path}")

        # Ensure #Shorts is in the title or description for YouTube Shorts algorithm
        if "#Shorts" not in title and "#shorts" not in title:
            title = f"{title[:90]} #Shorts"
        if "#Shorts" not in description and "#shorts" not in description:
            description = f"{description}\n\n#Shorts #viral #reels"

        youtube = googleapiclient.discovery.build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags or ["shorts", "viral", "openshorts"],
                "categoryId": "22"  # People & Blogs
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload YouTube: {int(status.progress() * 100)}%")

        video_id = response.get("id")
        video_url = f"https://www.youtube.com/shorts/{video_id}"
        logger.info(f"Short publicado com sucesso! {video_url}")
        return {
            "video_id": video_id,
            "url": video_url,
            "response": response
        }
