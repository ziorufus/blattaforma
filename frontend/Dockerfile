
FROM node:22-alpine AS build

WORKDIR /app

# Installa le dipendenze
COPY package*.json ./
RUN npm install

# Copia il progetto
COPY . .

# Compila il frontend
RUN npm run build


# Immagine finale
FROM node:22-alpine

WORKDIR /app

# Installa Vite per servire il build
COPY package*.json ./
RUN npm install --include=dev

COPY --from=build /app/dist ./dist
COPY --from=build /app/vite.config.js ./vite.config.js

EXPOSE 4173

CMD ["npx", "vite", "preview", \
     "--host", "0.0.0.0", \
     "--port", "4173", \
     "--strictPort"]
