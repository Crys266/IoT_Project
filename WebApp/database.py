from pymongo import MongoClient, ASCENDING, DESCENDING
from gridfs import GridFS
from datetime import datetime, timezone
from bson import ObjectId
import os
import json
import io
import cv2
import numpy as np
from typing import List, Dict, Optional, Any


class SurveillanceDB:
    def __init__(self, connection_string: str = "mongodb://db:27017/"):
        """
        Inizializza connessione MongoDB per sistema surveillance IoT con GridFS
        """
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Test connessione
            self.client.admin.command('ping')
            print("✅ MongoDB connection successful!")

            self.db = self.client.iot_surveillance
            self.images = self.db.surveillance_images
            self.sessions = self.db.esp32_sessions

            # GridFS per file binari
            self.gridfs_images = GridFS(self.db, collection="images")
            self.gridfs_thumbnails = GridFS(self.db, collection="thumbnails")

            self._setup_indexes()
            print("✅ Database indexes created")
            print("✅ GridFS collections initialized")

        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            print("💡 Make sure MongoDB is running on localhost:27017")
            raise

    def _setup_indexes(self):
        """Crea indici per performance ottimali"""
        try:
            # Indici esistenti per metadati
            self.images.create_index([("created_at", DESCENDING)])
            self.images.create_index([("location", "2dsphere")])
            self.images.create_index([("detection.objects_count", ASCENDING)])
            self.images.create_index([("detection.active", ASCENDING)])
            self.images.create_index([
                ("created_at", DESCENDING),
                ("detection.active", ASCENDING)
            ])
            self.images.create_index([("tags", ASCENDING)])
            self.images.create_index([("filename", ASCENDING)])

            # Indici GridFS per performance
            self.images.create_index([("gridfs_image_id", ASCENDING)])
            self.images.create_index([("gridfs_thumbnail_id", ASCENDING)])

        except Exception as e:
            print(f"⚠️ Warning creating indexes: {e}")

    def _create_thumbnail_from_bytes(self, image_bytes: bytes, size=(150, 150)) -> bytes:
        """
        Crea thumbnail in memoria da bytes immagine
        """
        try:
            # Decodifica immagine da bytes
            img_array = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                raise ValueError("Invalid image data")

            # Ridimensiona mantenendo aspect ratio
            h, w = img.shape[:2]
            aspect = w / h

            if aspect > 1:
                new_w, new_h = size[0], int(size[0] / aspect)
            else:
                new_w, new_h = int(size[1] * aspect), size[1]

            resized = cv2.resize(img, (new_w, new_h))

            # Codifica come JPEG
            ret, buffer = cv2.imencode('.jpg', resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not ret:
                raise ValueError("Failed to encode thumbnail")

            return buffer.tobytes()

        except Exception as e:
            print(f"❌ Error creating thumbnail: {e}")
            raise

    def save_image_to_gridfs(self, image_data: bytes, filename: str, metadata: Dict = None) -> str:
        """
        Salva immagine in GridFS e ritorna l'ObjectId
        """
        try:
            # Prepara metadati SENZA filename per evitare conflitto
            gridfs_metadata = {
                "content_type": "image/jpeg",
                "upload_date": datetime.now(timezone.utc)
            }

            # Aggiungi metadati custom solo se non in conflitto
            if metadata:
                for key, value in metadata.items():
                    if key != 'filename':  # Evita conflitto
                        gridfs_metadata[key] = value

            # Salva in GridFS - filename come parametro separato
            image_id = self.gridfs_images.put(
                image_data,
                filename=filename,
                **gridfs_metadata
            )

            print(f"✅ Image saved to GridFS: {image_id}")
            return str(image_id)

        except Exception as e:
            print(f"❌ Error saving image to GridFS: {e}")
            raise

    def save_thumbnail_to_gridfs(self, image_data: bytes, filename: str) -> str:
        """
        Crea e salva thumbnail in GridFS
        """
        try:
            # Crea thumbnail in memoria
            thumbnail_data = self._create_thumbnail_from_bytes(image_data)

            thumbnail_filename = f"thumb_{filename}"

            # Metadati thumbnail SENZA filename nel dict
            thumbnail_metadata = {
                "content_type": "image/jpeg",
                "upload_date": datetime.now(timezone.utc),
                "is_thumbnail": True,
                "original_filename": filename
            }

            # Salva thumbnail in GridFS
            thumbnail_id = self.gridfs_thumbnails.put(
                thumbnail_data,
                filename=thumbnail_filename,
                **thumbnail_metadata
            )

            print(f"✅ Thumbnail saved to GridFS: {thumbnail_id}")
            return str(thumbnail_id)

        except Exception as e:
            print(f"❌ Error saving thumbnail to GridFS: {e}")
            raise

    def get_image_from_gridfs(self, image_id: str) -> tuple:
        """
        Recupera immagine da GridFS
        Returns: (image_data, metadata)
        """
        try:
            if not ObjectId.is_valid(image_id):
                raise ValueError("Invalid ObjectId")

            grid_out = self.gridfs_images.get(ObjectId(image_id))
            image_data = grid_out.read()
            metadata = {
                "filename": grid_out.filename,
                "content_type": grid_out.content_type or "image/jpeg",
                "upload_date": grid_out.upload_date,
                "length": grid_out.length
            }

            return image_data, metadata

        except Exception as e:
            print(f"❌ Error getting image from GridFS: {e}")
            raise

    def get_thumbnail_from_gridfs(self, thumbnail_id: str) -> tuple:
        """
        Recupera thumbnail da GridFS
        Returns: (thumbnail_data, metadata)
        """
        try:
            if not ObjectId.is_valid(thumbnail_id):
                raise ValueError("Invalid ObjectId")

            grid_out = self.gridfs_thumbnails.get(ObjectId(thumbnail_id))
            thumbnail_data = grid_out.read()
            metadata = {
                "filename": grid_out.filename,
                "content_type": grid_out.content_type or "image/jpeg",
                "upload_date": grid_out.upload_date,
                "length": grid_out.length
            }

            return thumbnail_data, metadata

        except Exception as e:
            print(f"❌ Error getting thumbnail from GridFS: {e}")
            raise

    def delete_from_gridfs(self, image_id: str, thumbnail_id: str = None):
        """
        Elimina immagine e thumbnail da GridFS
        """
        try:
            if image_id and ObjectId.is_valid(image_id):
                self.gridfs_images.delete(ObjectId(image_id))
                print(f"✅ Deleted image from GridFS: {image_id}")

            if thumbnail_id and ObjectId.is_valid(thumbnail_id):
                self.gridfs_thumbnails.delete(ObjectId(thumbnail_id))
                print(f"✅ Deleted thumbnail from GridFS: {thumbnail_id}")

        except Exception as e:
            print(f"❌ Error deleting from GridFS: {e}")

    def get_dangerous_classes(self) -> list:
        doc = self.db.system_config.find_one({'_id': 'notification_config'})
        return doc.get('dangerous_classes', ['person']) if doc else ['person']

    def set_dangerous_classes(self, dangerous_classes: list):
        self.db.system_config.update_one(
            {'_id': 'notification_config'},
            {'$set': {'dangerous_classes': dangerous_classes}},
            upsert=True
        )

    def save_image_metadata(self, image_data: bytes, image_metadata: Dict[str, Any]) -> str:
        """
        Salva immagine completa (file + metadati) usando GridFS
        """
        try:
            filename = image_metadata["filename"]

            # Prepara metadati GridFS PULITI (senza filename)
            gridfs_image_metadata = {
                "gps": image_metadata.get("gps", "unknown"),
                "temperature": image_metadata.get("temperature"),
                "humidity": image_metadata.get("humidity"),
                "effects_negative": image_metadata.get("negative_effect", False),
                "effects_detection": image_metadata.get("detection_active", False)
            }

            print(f"🗄️ Saving image to GridFS: {filename}")
            image_id = self.save_image_to_gridfs(image_data, filename, gridfs_image_metadata)

            print(f"🖼️ Creating thumbnail for: {filename}")
            thumbnail_id = self.save_thumbnail_to_gridfs(image_data, filename)

            # Prepara documento metadati (senza percorsi filesystem)
            document = {
                "filename": filename,
                "gridfs_image_id": ObjectId(image_id),
                "gridfs_thumbnail_id": ObjectId(thumbnail_id),
                "size": len(image_data),
                "created_at": datetime.fromisoformat(image_metadata["created"]),
                "updated_at": datetime.now(timezone.utc),

                # Geospatial data
                "location": None,
                "gps_raw": {
                    "lat": image_metadata.get("gps_lat"),
                    "lon": image_metadata.get("gps_lon"),
                    "gps_string": image_metadata.get("gps", "unknown")
                },

                # Environmental data
                "environmental": {
                    "temperature": image_metadata.get("temperature"),
                    "humidity": image_metadata.get("humidity"),
                    "timestamp": datetime.now(timezone.utc)
                },

                # Detection results
                "detection": {
                    "active": image_metadata.get("detection_active", False),
                    "objects_count": 0,
                    "boxes": [],
                    "processing_time": 0,
                    "detection_timestamp": None
                },

                # Visual effects applied
                "effects": {
                    "negative": image_metadata.get("negative_effect", False),
                    "object_detection": image_metadata.get("detection_active", False)
                },

                # User metadata
                "tags": image_metadata.get("tags", []),
                "description": image_metadata.get("description", ""),
                "analysis": image_metadata.get("analysis"),

                # System metadata
                "esp32_session_id": self._get_current_session_id(),
                "system_version": "2.1_gridfs",
                "saved_by": image_metadata.get("saved_by", "system")
            }

            # Aggiungi coordinate GeoJSON se disponibili
            if image_metadata.get("gps_lat") and image_metadata.get("gps_lon"):
                document["location"] = {
                    "type": "Point",
                    "coordinates": [float(image_metadata["gps_lon"]), float(image_metadata["gps_lat"])]
                }

            # Aggiungi detection results se presenti
            if "detection_results" in image_metadata:
                detection = image_metadata["detection_results"]
                document["detection"].update({
                    "objects_count": detection.get("objects_count", 0),
                    "boxes": detection.get("boxes", []),
                    "processing_time": detection.get("processing_time", 0),
                    "detection_timestamp": datetime.fromtimestamp(detection.get("detection_time", 0),
                                                                  timezone.utc) if detection.get(
                        "detection_time") else None
                })

            # Inserisci metadati nel database
            result = self.images.insert_one(document)
            print(f"✅ Saved complete image with GridFS: {result.inserted_id}")
            return str(result.inserted_id)

        except Exception as e:
            print(f"❌ Error saving complete image: {e}")
            print(f"❌ Exception details: {type(e).__name__}: {str(e)}")
            # Cleanup in caso di errore
            try:
                if 'image_id' in locals():
                    print(f"🧹 Cleaning up image_id: {image_id}")
                    self.gridfs_images.delete(ObjectId(image_id))
                if 'thumbnail_id' in locals():
                    print(f"🧹 Cleaning up thumbnail_id: {thumbnail_id}")
                    self.gridfs_thumbnails.delete(ObjectId(thumbnail_id))
            except Exception as cleanup_error:
                print(f"⚠️ Cleanup error: {cleanup_error}")
            raise

    def get_images_paginated(self, page: int = 1, limit: int = 20, filters: Optional[Dict] = None) -> Dict:
        """
        Recupera immagini con paginazione (metadati + riferimenti GridFS)
        """
        try:
            # Build query
            query = {}
            if filters:
                if filters.get("has_detection"):
                    query["detection.objects_count"] = {"$gt": 0}
                if filters.get("date_from"):
                    query["created_at"] = {"$gte": datetime.fromisoformat(filters["date_from"])}
                if filters.get("date_to"):
                    if "created_at" not in query:
                        query["created_at"] = {}
                    query["created_at"]["$lte"] = datetime.fromisoformat(filters["date_to"])
                if filters.get("tags"):
                    query["tags"] = {"$in": filters["tags"]}

            # Calcola skip per paginazione
            skip = (page - 1) * limit

            # Query con sort (più recenti prima)
            cursor = self.images.find(query).sort("created_at", DESCENDING).skip(skip).limit(limit)

            # Converti in formato compatibile con frontend
            images = []
            for doc in cursor:
                img = self._mongodb_to_legacy_format(doc)
                images.append(img)

            # Conta totali
            total_count = self.images.count_documents(query)
            total_size = self._calculate_total_size(query)

            return {
                "images": images,
                "pagination": {
                    "current_page": page,
                    "per_page": limit,
                    "total_pages": (total_count + limit - 1) // limit,
                    "total_count": total_count
                },
                "statistics": {
                    "total_images": total_count,
                    "total_size": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2)
                }
            }

        except Exception as e:
            print(f"❌ Error getting paginated images: {e}")
            return {"images": [], "pagination": {}, "statistics": {}}

    def delete_image(self, image_id: str) -> bool:
        """
        Elimina immagine completa (metadati + GridFS files)
        """
        try:
            if not ObjectId.is_valid(image_id):
                return False

            # Trova metadati per ottenere GridFS IDs
            image_doc = self.images.find_one({"_id": ObjectId(image_id)})
            if not image_doc:
                return False

            # Elimina da GridFS
            gridfs_image_id = image_doc.get("gridfs_image_id")
            gridfs_thumbnail_id = image_doc.get("gridfs_thumbnail_id")

            self.delete_from_gridfs(str(gridfs_image_id), str(gridfs_thumbnail_id))

            # Elimina metadati
            result = self.images.delete_one({"_id": ObjectId(image_id)})

            print(f"✅ Completely deleted image: {image_id}")
            return result.deleted_count > 0

        except Exception as e:
            print(f"❌ Error deleting image: {e}")
            return False

    def _mongodb_to_legacy_format(self, doc: Dict) -> Dict:
        """
        Converte documento MongoDB nel formato legacy per compatibilità frontend
        """
        result = {
            "id": str(doc["_id"]),
            "filename": doc["filename"],
            "gridfs_image_id": str(doc["gridfs_image_id"]),
            "gridfs_thumbnail_id": str(doc["gridfs_thumbnail_id"]),
            "size": doc["size"],
            "created": doc["created_at"].isoformat(),
            "gps": doc["gps_raw"]["gps_string"],
            "gps_lat": doc["gps_raw"]["lat"],
            "gps_lon": doc["gps_raw"]["lon"],
            "temperature": doc["environmental"]["temperature"],
            "humidity": doc["environmental"]["humidity"],
            "tags": doc["tags"],
            "description": doc["description"],
            "analysis": doc["analysis"],
            "detection_results": {
                "boxes": doc["detection"]["boxes"],
                "objects_count": doc["detection"]["objects_count"],
                "detection_time": doc["detection"]["detection_timestamp"].timestamp() if doc["detection"][
                    "detection_timestamp"] else None,
                "processing_time": doc["detection"]["processing_time"]
            } if doc["detection"]["objects_count"] > 0 else None,
            "negative_effect": doc["effects"]["negative"],
            "detection_active": doc["detection"]["active"],
            "saved_by": doc.get("saved_by", "unknown"),
            # ✅ QUESTO ERA MANCANTE! Frontend si aspetta questo campo
            "thumbnail": f"thumb_{doc['filename']}"
        }

        print(f"🔍 Generated legacy format for {doc['filename']}: thumbnail={result['thumbnail']}")
        return result
    # Metodi esistenti invariati...
    def find_images_near_location(self, lat: float, lon: float, radius_km: float = 1.0) -> List[Dict]:
        """Query geospaziali - trova immagini vicine a coordinate specifiche"""
        try:
            query = {
                "location": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        },
                        "$maxDistance": radius_km * 1000
                    }
                }
            }
            cursor = self.images.find(query).sort("created_at", DESCENDING)
            return [self._mongodb_to_legacy_format(doc) for doc in cursor]
        except Exception as e:
            print(f"❌ Error in geospatial query: {e}")
            return []

    def get_detection_statistics(self, date_range: Optional[tuple] = None) -> Dict:
        """Statistiche avanzate su object detection usando aggregation pipeline"""
        try:
            match_stage = {}
            if date_range:
                match_stage["created_at"] = {
                    "$gte": datetime.fromisoformat(date_range[0]),
                    "$lte": datetime.fromisoformat(date_range[1])
                }

            pipeline = []
            if match_stage:
                pipeline.append({"$match": match_stage})

            pipeline.extend([
                {
                    "$group": {
                        "_id": None,
                        "total_images": {"$sum": 1},
                        "images_with_detection": {
                            "$sum": {"$cond": [{"$gt": ["$detection.objects_count", 0]}, 1, 0]}
                        },
                        "total_objects_detected": {"$sum": "$detection.objects_count"},
                        "avg_objects_per_image": {"$avg": "$detection.objects_count"},
                        "avg_processing_time": {"$avg": "$detection.processing_time"}
                    }
                }
            ])

            result = list(self.images.aggregate(pipeline))

            label_pipeline = []
            if match_stage:
                label_pipeline.append({"$match": match_stage})

            label_pipeline.extend([
                {"$unwind": "$detection.boxes"},
                {
                    "$group": {
                        "_id": "$detection.boxes.label",
                        "count": {"$sum": 1},
                        "avg_confidence": {"$avg": "$detection.boxes.confidence"}
                    }
                },
                {"$sort": {"count": -1}}
            ])

            label_stats = list(self.images.aggregate(label_pipeline))

            return {
                "general": result[0] if result else {},
                "by_label": label_stats,
                "date_range": date_range
            }

        except Exception as e:
            print(f"❌ Error getting detection statistics: {e}")
            return {}

    def update_image_metadata(self, image_id: str, updates: Dict) -> bool:
        """Aggiorna metadati immagine"""
        try:
            if not ObjectId.is_valid(image_id):
                return False
            update_doc = {"$set": {**updates, "updated_at": datetime.now(timezone.utc)}}
            result = self.images.update_one({"_id": ObjectId(image_id)}, update_doc)
            return result.modified_count > 0
        except Exception as e:
            print(f"❌ Error updating image: {e}")
            return False

    def _calculate_total_size(self, query: Dict) -> int:
        """Calcola dimensione totale dei file per la query"""
        try:
            pipeline = [
                {"$match": query},
                {"$group": {"_id": None, "total_size": {"$sum": "$size"}}}
            ]
            result = list(self.images.aggregate(pipeline))
            return result[0]["total_size"] if result else 0
        except:
            return 0

    def _get_current_session_id(self) -> str:
        """Genera/recupera session ID per tracking ESP32"""
        return f"esp32_session_{int(datetime.now().timestamp())}"

    def get_database_stats(self) -> Dict:
        """Statistiche generali del database per monitoring"""
        try:
            stats = self.db.command("dbStats")
            collection_stats = self.db.command("collStats", "surveillance_images")

            # Statistiche GridFS
            try:
                gridfs_images_stats = self.db.command("collStats", "images.files")
                gridfs_thumbnails_stats = self.db.command("collStats", "thumbnails.files")
                gridfs_data = {
                    "images_files": gridfs_images_stats.get("count", 0),
                    "images_size": gridfs_images_stats.get("size", 0),
                    "thumbnails_files": gridfs_thumbnails_stats.get("count", 0),
                    "thumbnails_size": gridfs_thumbnails_stats.get("size", 0)
                }
            except:
                gridfs_data = {
                    "images_files": 0,
                    "images_size": 0,
                    "thumbnails_files": 0,
                    "thumbnails_size": 0
                }

            return {
                "database": {
                    "collections": stats["collections"],
                    "data_size": stats["dataSize"],
                    "storage_size": stats["storageSize"],
                    "indexes": stats["indexes"],
                    "index_size": stats["indexSize"]
                },
                "images_collection": {
                    "count": collection_stats["count"],
                    "size": collection_stats["size"],
                    "avg_obj_size": collection_stats.get("avgObjSize", 0)
                },
                "gridfs": gridfs_data
            }
        except Exception as e:
            print(f"❌ Error getting database stats: {e}")
            return {}




def create_surveillance_db(connection_string: str = None) -> SurveillanceDB:
    """Crea istanza database con GridFS"""
    if connection_string is None:
        connection_string = os.getenv("MONGODB_URI", "mongodb://db:27017/")
    return SurveillanceDB(connection_string)
