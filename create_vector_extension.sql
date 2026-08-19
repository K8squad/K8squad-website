-- Create vector extension if not exists
DO $$
BEGIN
   IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
      CREATE EXTENSION vector;
      RAISE NOTICE 'Extension "vector" created successfully';
   ELSE
      RAISE NOTICE 'Extension "vector" already exists';
   END IF;
END $$;