from pymongo import MongoClient, ASCENDING, DESCENDING
from datetime import datetime, timezone
from bson import ObjectId
import os
import json
from typing import List, Dict, Optional, Any


class SurveillanceDB:
    def __init__(self, connection_string: str = "mongodb://localhost:27017/"):
        """
        Inizializza connessione MongoDB per sistema surveillance IoT
        """
        try:
            self.client = MongoClient(connection_string, serverSelectionTimeoutMS=5000)
            # Test connessione
            self.client.admin.command('ping')
            print("✅ MongoDB connection successful!")

            self.db = self.client.iot_surveillance
            self.images = self.db.surveillance_images
            self.sessions = self.db.esp32_sessions  # Per tracking sessioni ESP32

            self._setup_indexes()
            print("✅ Database indexes created")

        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            print("💡 Make sure MongoDB is running on localhost:27017")
            raise

    def _setup_indexes(self):
        """Crea indici per performance ottimali"""
        try:
            # Indice temporale (più recenti prima)
            self.images.create_index([("created_at", DESCENDING)])

            # Indice geospaziale per query geografiche
            self.images.create_index([("location", "2dsphere")])

            # Indici per detection
            self.images.create_index([("detection.objects_count", ASCENDING)])
            self.images.create_index([("detection.active", ASCENDING)])

            # Indice composto per query comuni (recenti + con detection)
            self.images.create_index([
                ("created_at", DESCENDING),
                ("detection.active", ASCENDING)
            ])

            # Indici per search e filtering
            self.images.create_index([("tags", ASCENDING)])
            self.images.create_index([("filename", ASCENDING)])

        except Exception as e:
            print(f"⚠️ Warning creating indexes: {e}")

    def save_image_metadata(self, image_data: Dict[str, Any]) -> str:
        """
        Salva metadati immagine nel database
        Returns: MongoDB ObjectId as string
        """
        try:
            # Prepara documento per MongoDB
            document = {
                "filename": image_data["filename"],
                "filepath": image_data["filepath"],
                "thumbnail_path": image_data.get("thumbnail", ""),
                "size": image_data["size"],
                "created_at": datetime.fromisoformat(image_data["created"]),
                "updated_at": datetime.now(timezone.utc),

                # Geospatial data (formato GeoJSON)
                "location": None,
                "gps_raw": {
                    "lat": image_data.get("gps_lat"),
                    "lon": image_data.get("gps_lon"),
                    "gps_string": image_data.get("gps", "unknown")
                },

                # Environmental data
                "environmental": {
                    "temperature": image_data.get("temperature"),
                    "humidity": image_data.get("humidity"),
                    "timestamp": datetime.now(timezone.utc)
                },

                # Detection results
                "detection": {
                    "active": image_data.get("detection_active", False),
                    "objects_count": 0,
                    "boxes": [],
                    "processing_time": 0,
                    "detection_timestamp": None
                },

                # Visual effects applied
                "effects": {
                    "negative": image_data.get("negative_effect", False),
                    "object_detection": image_data.get("detection_active", False)
                },

                # User metadata
                "tags": image_data.get("tags", []),
                "description": image_data.get("description", ""),
                "analysis": image_data.get("analysis"),

                # System metadata
                "esp32_session_id": self._get_current_session_id(),
                "system_version": "2.0_mongodb"
            }

            # Aggiungi coordinate GeoJSON se disponibili
            if image_data.get("gps_lat") and image_data.get("gps_lon"):
                document["location"] = {
                    "type": "Point",
                    "coordinates": [float(image_data["gps_lon"]), float(image_data["gps_lat"])]
                }

            # Aggiungi detection results se presenti
            if "detection_results" in image_data:
                detection = image_data["detection_results"]
                document["detection"].update({
                    "objects_count": detection.get("objects_count", 0),
                    "boxes": detection.get("boxes", []),
                    "processing_time": detection.get("processing_time", 0),
                    "detection_timestamp": datetime.fromtimestamp(detection.get("detection_time", 0),
                                                                  timezone.utc) if detection.get(
                        "detection_time") else None
                })

            # Inserisci nel database
            result = self.images.insert_one(document)
            print(f"✅ Saved image to MongoDB: {result.inserted_id}")
            return str(result.inserted_id)

        except Exception as e:
            print(f"❌ Error saving image to MongoDB: {e}")
            raise

    def get_images_paginated(self, page: int = 1, limit: int = 20, filters: Optional[Dict] = None) -> Dict:
        """
        Recupera immagini con paginazione e filtri avanzati
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

    def find_images_near_location(self, lat: float, lon: float, radius_km: float = 1.0) -> List[Dict]:
        """
        Query geospaziali - trova immagini vicine a coordinate specifiche
        """
        try:
            query = {
                "location": {
                    "$near": {
                        "$geometry": {
                            "type": "Point",
                            "coordinates": [lon, lat]
                        },
                        "$maxDistance": radius_km * 1000  # Convert km to meters
                    }
                }
            }

            cursor = self.images.find(query).sort("created_at", DESCENDING)
            return [self._mongodb_to_legacy_format(doc) for doc in cursor]

        except Exception as e:
            print(f"❌ Error in geospatial query: {e}")
            return []

    def get_detection_statistics(self, date_range: Optional[tuple] = None) -> Dict:
        """
        Statistiche avanzate su object detection usando aggregation pipeline
        """
        try:
            # Build match stage per date range
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
                # Statistiche generali
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

            # Statistiche per label
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

    def delete_image(self, image_id: str) -> bool:
        """
        Elimina immagine dal database
        """
        try:
            if not ObjectId.is_valid(image_id):
                return False

            result = self.images.delete_one({"_id": ObjectId(image_id)})
            return result.deleted_count > 0

        except Exception as e:
            print(f"❌ Error deleting image: {e}")
            return False

    def update_image_metadata(self, image_id: str, updates: Dict) -> bool:
        """
        Aggiorna metadati immagine
        """
        try:
            if not ObjectId.is_valid(image_id):
                return False

            # Prepara update con timestamp
            update_doc = {"$set": {**updates, "updated_at": datetime.now(timezone.utc)}}

            result = self.images.update_one(
                {"_id": ObjectId(image_id)},
                update_doc
            )
            return result.modified_count > 0

        except Exception as e:
            print(f"❌ Error updating image: {e}")
            return False

    def _mongodb_to_legacy_format(self, doc: Dict) -> Dict:
        """
        Converte documento MongoDB nel formato legacy per compatibilità frontend
        """
        return {
            "id": str(doc["_id"]),
            "filename": doc["filename"],
            "filepath": doc["filepath"],
            "thumbnail": doc.get("thumbnail_path", ""),
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
            "detection_active": doc["detection"]["active"]
        }

    def _calculate_total_size(self, query: Dict) -> int:
        """
        Calcola dimensione totale dei file per la query
        """
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
        """
        Genera/recupera session ID per tracking ESP32
        """
        # Per ora ritorna timestamp, ma potresti implementare logic più sofisticata
        return f"esp32_session_{int(datetime.now().timestamp())}"

    def migrate_from_json(self, json_file_path: str) -> Dict:
        """
        Migra dati esistenti da file JSON a MongoDB
        """
        try:
            if not os.path.exists(json_file_path):
                return {"status": "error", "message": f"File {json_file_path} not found"}

            with open(json_file_path, 'r') as f:
                legacy_data = json.load(f)

            migrated_count = 0
            errors = []

            for item in legacy_data:
                try:
                    # Controlla se già esiste (per evitare duplicati)
                    existing = self.images.find_one({"filename": item["filename"]})
                    if existing:
                        print(f"⚠️ Skipping duplicate: {item['filename']}")
                        continue

                    self.save_image_metadata(item)
                    migrated_count += 1

                except Exception as e:
                    errors.append(f"Error migrating {item.get('filename', 'unknown')}: {e}")

            return {
                "status": "success",
                "migrated_count": migrated_count,
                "total_items": len(legacy_data),
                "errors": errors
            }

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_database_stats(self) -> Dict:
        """
        Statistiche generali del database per monitoring
        """
        try:
            stats = self.db.command("dbStats")
            collection_stats = self.db.command("collStats", "surveillance_images")

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
                    "avg_obj_size": collection_stats["avgObjSize"]
                }
            }
        except Exception as e:
            print(f"❌ Error getting database stats: {e}")
            return {}


# Factory function per facile inizializzazione
def create_surveillance_db(connection_string: str = None) -> SurveillanceDB:
    """
    Crea istanza database con configurazione automatica
    """
    if connection_string is None:
        connection_string = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")

    return SurveillanceDB(connection_string)